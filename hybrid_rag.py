"""
hybrid_rag.py — Core Hybrid RAG Engine (Vector + Graph over any codebase)
============================================================================
อิงจาก Session 12 (Hybrid RAG Engine) + Session 13 (Coding Assistant) เป็นหลัก

โครงสร้างการทำงาน:

    User question
         |
         v
    QuestionRouter (keyword tier 1, LLM tier 2 = เผื่ออัพเกรด ปิดไว้ก่อน)
         |
    ┌────┴─────────┐
    v               v
  graph            vector
  (Kuzu call graph) (FAISS — function-level chunk จาก AST)
         |
         v
    qwen2.5-coder:7b (generate คำตอบ)

ระบบรองรับการ index "โฟลเดอร์โค้ดอะไรก็ได้" ไม่ผูกกับโปรเจกต์ตัวอย่างเดียว —
ทุกครั้งที่ index โฟลเดอร์ใหม่ จะได้ vector_db/graph_db แยกชื่อตามโฟลเดอร์นั้น
(ดู index_metadata.json ว่าตอนนี้ระบบ "แอคทีฟ" อยู่กับโฟลเดอร์ไหน)

รันเทส engine ตรงๆ (ไม่ผ่าน UI): python hybrid_rag.py
"""

import ast
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MODEL_LLM = "qwen2.5-coder:7b"          # generation model (5-8B)
MODEL_EMBED_CODE = "nomic-embed-text"    # embedding สำหรับ codebase (FAISS)

METADATA_PATH = "index_metadata.json"    # บอกว่าตอนนี้ active อยู่กับ vector_db/graph_db ไหน

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"

TOP_K_CODE = 5
KEEP_ALIVE = "30m"

IGNORE_DIR_NAMES = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}

# ─── Tier 2: LLM fallback router — เผื่ออัพเกรด ───────────────────────────────
# ปิดไว้ก่อนเพื่อความเร็ว/ความชัวร์ตอนใกล้ deadline พร้อมเปิดได้ทันที
# (set ENABLE_LLM_ROUTER_DEFAULT = True หรือส่ง enable_llm_router=True ตอนสร้าง HybridRAG)
ENABLE_LLM_ROUTER_DEFAULT = False


# ═════════════════════════════════════════════════════════════════════════════
#  Ollama helpers (chat + embed) — เรียกตรงผ่าน HTTP ไม่พึ่ง SDK เพิ่ม
# ═════════════════════════════════════════════════════════════════════════════

def ollama_embed(texts: list[str], model: str = MODEL_EMBED_CODE) -> list[list[float]]:
    payload = {"model": model, "input": texts, "keep_alive": KEEP_ALIVE}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_EMBED_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["embeddings"]


def ollama_chat(prompt: str, model: str = MODEL_LLM, temperature: float = 0.0) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_CHAT_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["message"]["content"]


def ollama_chat_stream(prompt: str, model: str = MODEL_LLM, temperature: float = 0.0):
    """generator: yield คำตอบทีละ token (เผื่ออัพเกรด UI ให้ stream ทีหลัง)"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_CHAT_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
            if chunk.get("done"):
                break


# ═════════════════════════════════════════════════════════════════════════════
#  Codebase scanning / AST helpers — ใช้ index โฟลเดอร์ไหนก็ได้
# ═════════════════════════════════════════════════════════════════════════════

def find_python_files(directory: str) -> list[Path]:
    result = []
    for p in Path(directory).rglob("*.py"):
        if any(part in IGNORE_DIR_NAMES for part in p.parts):
            continue
        result.append(p)
    return sorted(result)


def extract_function_chunks(filepath: str) -> list[dict]:
    """Parse ไฟล์ .py แล้ว extract ทุก function เป็น chunk พร้อม metadata (สำหรับ FAISS)"""
    try:
        source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=filepath)
    except Exception as e:
        print(f"  Warning: Cannot parse {filepath}: {e}")
        return []

    chunks = []
    lines = source.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 20)
            code = "\n".join(lines[start:end])
            chunks.append({"name": node.name, "code": code, "file": filepath, "line_start": node.lineno})
    return chunks


class _ScopedCallCollector(ast.NodeVisitor):
    """เก็บ Call node เฉพาะที่อยู่ใน scope นี้ตรงๆ (ไม่ลงไปนับซ้ำใน nested def/class)"""

    def __init__(self):
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call):
        callee = None
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        if callee:
            self.calls.append(callee)
        self.generic_visit(node)  # เผื่อมี call ซ้อน call เช่น f(g(x))

    def visit_FunctionDef(self, node):
        pass  # ไม่ลงไปนับ — nested function จะถูกเก็บแยกเป็น entry ของตัวเอง

    def visit_AsyncFunctionDef(self, node):
        pass

    def visit_ClassDef(self, node):
        pass


class _FunctionCollector(ast.NodeVisitor):
    """เดิน AST ทั้งไฟล์ เก็บ (qualified_name, calls) โดยรวมชื่อ class ที่ครอบไว้ด้วย
    เพื่อไม่ให้ 2 เมธอดชื่อเดียวกันในคนละ class (เช่น __init__) ชนกัน (primary key ซ้ำใน Kuzu)"""

    def __init__(self, filepath: str, module_name: str):
        self.filepath = filepath
        self.functions: list[dict] = []
        self.edges: list[tuple[str, str]] = []
        self.stack = [module_name]
        self._seen_names: set[str] = set()

    def _qualname(self, name: str) -> str:
        return ".".join(self.stack + [name])

    def visit_ClassDef(self, node: ast.ClassDef):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _handle_function(self, node):
        fq_name = self._qualname(node.name)
        if fq_name in self._seen_names:
            # เจอชื่อซ้ำในสโคปเดียวกัน (เช่น @overload หลายอันก่อนถึง implementation จริง) -> กันชนกัน
            suffix = 2
            while f"{fq_name}#{suffix}" in self._seen_names:
                suffix += 1
            fq_name = f"{fq_name}#{suffix}"
        self._seen_names.add(fq_name)
        self.functions.append({"name": fq_name, "file": self.filepath, "line": node.lineno})

        collector = _ScopedCallCollector()
        for child in ast.iter_child_nodes(node):
            collector.visit(child)
        for callee in collector.calls:
            self.edges.append((fq_name, callee))

        self.stack.append(node.name)
        self.generic_visit(node)  # ลงไปเก็บ nested function/class ต่อ (ชื่อจะ unique เพราะ stack ยาวขึ้น)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node)


def extract_call_edges(filepath: str, root: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Parse ไฟล์ .py คืน ([function nodes ({name, file, line})], [(caller_fq, callee_short), ...])
    ชื่อ function จะรวม class ที่ครอบไว้ด้วย เช่น 'adapters.HTTPAdapter.__init__' กัน primary key ชนกัน"""
    try:
        source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=filepath)
    except Exception as e:
        print(f"  Warning: Cannot parse {filepath}: {e}")
        return [], []

    module_name = str(Path(filepath).relative_to(root)).replace("\\", "/").replace(".py", "").replace("/", ".")
    collector = _FunctionCollector(str(filepath), module_name)
    collector.visit(tree)
    return collector.functions, collector.edges


def extract_function_name(question: str) -> Optional[str]:
    """หา function name ที่ถูกพูดถึงในคำถาม (เช่น 'Who calls get?' -> 'get', 'What does `Session.get` call?' -> 'Session.get')"""
    # ชื่อใน backtick มาก่อนเสมอ เช่น `merge_setting` หรือ `Response.json()`
    m = re.search(r"`([^`]+)`", question)
    if m:
        return re.sub(r"\(.*\)$", "", m.group(1).strip())
    words = [w.strip(".") for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", question)]
    trigger = {"calls", "call", "called", "uses", "use", "imports", "import"}
    stop = {"what", "who", "which", "does", "do", "is", "are", "function", "the", "functions", "in", "by"}
    for i, w in enumerate(words):
        if w.lower() in trigger:
            if i > 0:
                candidate = words[i - 1].strip("'\".,")
                if candidate.lower() not in stop:
                    return candidate
            if i + 1 < len(words):
                candidate = words[i + 1].strip("'\".,")
                if candidate.lower() not in stop:
                    return candidate
    # คำถามภาษาไทย (ไม่มี trigger ภาษาอังกฤษ) -> ใช้คำภาษาอังกฤษคำแรกที่ไม่ใช่ stop word เช่น 'ใครเรียก request บ้าง' -> 'request'
    for w in words:
        if w and w.lower() not in stop:
            return w
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  Indexing — สร้าง FAISS vector store + Kuzu graph db จากโฟลเดอร์ที่เลือก
#  (เรียกจากหน้า Codebase Indexer ของ Streamlit หรือจาก CLI)
# ═════════════════════════════════════════════════════════════════════════════

def build_vector_store(py_files: list[Path], out_path: str, progress_cb=None) -> dict:
    """คืน {"function_count", "file_count", "functions": [...], "files": [...]}"""
    from langchain_core.documents import Document
    from langchain_ollama import OllamaEmbeddings
    from langchain_community.vectorstores import FAISS

    all_chunks = []
    for i, py_file in enumerate(py_files, start=1):
        chunks = extract_function_chunks(str(py_file))
        all_chunks.extend(chunks)
        if progress_cb:
            progress_cb(f"Parsing {i}/{len(py_files)}: {py_file.name} ({len(chunks)} functions)")

    docs = [
        Document(page_content=c["code"], metadata={"function": c["name"], "file": c["file"], "line": c["line_start"]})
        for c in all_chunks
    ]
    if not docs:
        return {"function_count": 0, "file_count": len(py_files), "functions": [], "files": []}

    if progress_cb:
        progress_cb(f"Embedding {len(docs)} chunks ด้วย {MODEL_EMBED_CODE} (อาจใช้เวลา 1-2 นาที)...")
    embeddings = OllamaEmbeddings(model=MODEL_EMBED_CODE)
    vectorstore = FAISS.from_documents(docs, embeddings)
    vectorstore.save_local(out_path)

    return {
        "function_count": len(docs),
        "file_count": len(py_files),
        "functions": sorted({c["name"] for c in all_chunks}),
        "files": sorted({Path(c["file"]).stem for c in all_chunks}),
    }


def _reset_kuzu_path(out_path: str, attempts: int = 5, delay: float = 0.3) -> None:
    """ลบ graph_db เก่า (ไฟล์เดี่ยวในเวอร์ชัน kuzu ใหม่ หรือโฟลเดอร์ในเวอร์ชันเก่า) ก่อนสร้างใหม่

    บน Windows การลบไฟล์/โฟลเดอร์แล้วสร้างซ้ำที่ path เดิมทันที บางครั้งชนกับ
    การลบที่ยังไม่เสร็จจริงในระดับ OS (เช่น antivirus/indexer ถือ handle ค้าง) ทำให้
    kuzu.Database(out_path) โยน OSError [WinError 267] The directory name is invalid
    ทั้งที่โค้ดลบไฟล์ไปแล้ว — วน retry สั้นๆ ให้ทน race นี้แทนที่จะพังทันที
    """
    import shutil

    out_p = Path(out_path)
    for i in range(attempts):
        try:
            if out_p.is_dir():
                shutil.rmtree(out_p)
            elif out_p.exists():
                out_p.unlink()
            if not out_p.exists():
                return
        except OSError:
            pass
        time.sleep(delay)


def build_graph_db(py_files: list[Path], root: str, out_path: str, progress_cb=None) -> int:
    """คืนจำนวน call edges ที่สร้างได้"""
    import kuzu

    _reset_kuzu_path(out_path)

    db = None
    for attempt in range(5):
        try:
            db = kuzu.Database(out_path)
            break
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.3)
            _reset_kuzu_path(out_path)
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Function(name STRING, file STRING, line INT64, PRIMARY KEY (name))")
    conn.execute("CREATE REL TABLE IF NOT EXISTS CALLS(FROM Function TO Function)")

    all_functions, all_edges = [], []
    for i, py_file in enumerate(py_files, start=1):
        functions, edges = extract_call_edges(str(py_file), root)
        all_functions.extend(functions)
        all_edges.extend(edges)
        if progress_cb:
            progress_cb(f"Parsing call graph {i}/{len(py_files)}: {py_file.name}")

    known_names = {fn["name"] for fn in all_functions}
    for fn in all_functions:
        conn.execute(
            "MERGE (:Function {name: $n, file: $f, line: $l})",
            {"n": fn["name"], "f": fn["file"], "l": fn["line"]},
        )

    # หมายเหตุสำคัญ: ต้องเช็คก่อนว่า callee เป็น node ที่สร้างไปแล้วหรือยัง (จาก loop ด้านบน)
    # ถ้าใช่ ห้าม MERGE ซ้ำด้วย property ต่างกัน (file/line) เพราะ Kuzu MERGE จับคู่ทั้ง pattern
    # ไม่ใช่แค่ primary key — ถ้า property ไม่ตรงจะพยายาม CREATE ใหม่แล้วชน primary key ซ้ำ (บั๊กที่เจอมาก่อน)
    seen_edges = set()
    edge_count = 0
    if progress_cb:
        progress_cb(f"กำลังสร้าง call edges (~{len(all_edges)} รายการ) ...")
    for caller, callee in all_edges:
        matches = [n for n in known_names if n == callee or n.endswith(f".{callee}")]
        if matches:
            callee_fq = matches[0]  # node นี้มีอยู่แล้วจาก all_functions loop — ไม่ MERGE ซ้ำ
        else:
            callee_fq = f"external.{callee}"
            conn.execute("MERGE (:Function {name: $n, file: '', line: 0})", {"n": callee_fq})

        key = (caller, callee_fq)
        if key in seen_edges:
            continue
        seen_edges.add(key)

        conn.execute(
            "MATCH (a:Function), (b:Function) WHERE a.name = $a AND b.name = $b MERGE (a)-[:CALLS]->(b)",
            {"a": caller, "b": callee_fq},
        )
        edge_count += 1

    return edge_count


def index_folder(source_dir: str, progress_cb=None) -> dict:
    """
    Index โฟลเดอร์ที่เลือก -> สร้าง <basename>_vector_db/ + <basename>_graph_db/
    แล้วเขียน index_metadata.json ให้เป็น active index (chat page จะอ่านไฟล์นี้)
    """
    source_path = Path(source_dir).resolve()
    basename = source_path.name
    vector_db_path = f"{basename}_vector_db"
    graph_db_path = f"{basename}_graph_db"

    if progress_cb:
        progress_cb(f"Scanning {source_dir} ...")
    py_files = find_python_files(str(source_path))
    if progress_cb:
        progress_cb(f"พบ {len(py_files)} ไฟล์ .py (รวม subfolder, ข้าม .git/__pycache__/venv)")

    if not py_files:
        raise ValueError(f"ไม่พบไฟล์ .py ใน {source_dir}")

    vec_info = build_vector_store(py_files, vector_db_path, progress_cb=progress_cb)
    edge_count = build_graph_db(py_files, str(source_path), graph_db_path, progress_cb=progress_cb)

    metadata = {
        "source_dir": str(source_path),
        "basename": basename,
        "vector_db_path": vector_db_path,
        "graph_db_path": graph_db_path,
        "file_count": vec_info["file_count"],
        "function_count": vec_info["function_count"],
        "call_edge_count": edge_count,
        "functions": vec_info["functions"],
        "files": vec_info["files"],
        "indexed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    Path(METADATA_PATH).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if progress_cb:
        progress_cb(
            f"เสร็จแล้ว: {vec_info['function_count']} functions, {edge_count} call edges "
            f"จาก {vec_info['file_count']} ไฟล์"
        )
    return metadata


def load_active_metadata() -> Optional[dict]:
    p = Path(METADATA_PATH)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def clear_active_index() -> None:
    """ลบ index_metadata.json (ไม่ลบ vector_db/graph_db บนดิสก์) — กลับสู่สถานะ 'ยังไม่เคย index'"""
    p = Path(METADATA_PATH)
    if p.exists():
        p.unlink()


# ═════════════════════════════════════════════════════════════════════════════
#  Router — 2 ทาง (graph / vector) ตาม lab 12, เลือกอัตโนมัติจากคำถาม
# ═════════════════════════════════════════════════════════════════════════════

GRAPH_KEYWORDS = [
    "calls", "called by", "who calls", "what calls",
    "call hierarchy", "call chain", "references", "referenced by",
    "imports", "imported by", "inherits", "extends",
    "depends on", "dependency", "impact", "affects", "affected by",
    "which functions", "what functions", "defined in", "in which file",
    "used by", "callers", "callees",
    "ใครเรียก", "ไหนเรียก", "ถูกเรียก", "เรียกอะไร", "เรียกใช้โดย", "กระทบ",
]

# regex สำหรับรูปประโยคที่ keyword ตรงๆ จับไม่ได้ เช่น "What does Session.get call?"
GRAPH_PATTERNS = [
    r"\bwho\s+(calls|uses|imports)\b",
    r"\b(what|which)\s+(functions?|methods?)\s+(call|use|import)",
    r"\b(what|which)\s+does\s+\S+\s+(call|use|import)\b",
    r"\bcall(s|ed|ers|ees)?\b\s+`?\w",
    r"\bcall\s*\??$",
]

# คำถามให้เขียนโค้ดใหม่ ไม่ควรไป graph แม้มีคำว่า "เรียก"/"call"
CODEGEN_HINTS = ["เขียน", "write a", "write me", "create a function", "implement", "generate"]


def detect_call_direction(question: str) -> str:
    """'callees' = ถามว่า X เรียกอะไร, 'callers' = ถามว่าใครเรียก X"""
    q = question.lower()
    if re.search(r"\b(what|which)\s+(does|do|did)\b.*\bcall\b", q) or "เรียกอะไร" in q or "callees" in q:
        return "callees"
    return "callers"


class QuestionRouter:
    """
    Tier 1: GRAPH_KEYWORDS -> graph
    Tier 2: (เผื่ออัพเกรด, ปิดไว้เป็นค่าเริ่มต้น) ambiguous -> LLM classify
    ค่าเริ่มต้นสุดท้าย -> vector (ถามเกี่ยวกับโค้ด/แนวคิด ให้ FAISS ค้นหาก่อนเสมอ)
    """

    def __init__(self, enable_llm_router: bool = ENABLE_LLM_ROUTER_DEFAULT):
        self.enable_llm_router = enable_llm_router
        self._llm_router: Optional["LLMQuestionRouter"] = None

    def classify(self, question: str) -> dict:
        q_lower = question.lower()

        if any(h in q_lower for h in CODEGEN_HINTS):
            return {"route": "vector", "method": "codegen_hint", "reason": "asks to write new code"}

        for kw in GRAPH_KEYWORDS:
            if kw in q_lower:
                return {"route": "graph", "method": "keyword_graph", "reason": f"matched keyword '{kw}'"}

        for pat in GRAPH_PATTERNS:
            if re.search(pat, q_lower):
                return {"route": "graph", "method": "pattern_graph", "reason": f"matched pattern '{pat}'"}

        if self.enable_llm_router:
            if self._llm_router is None:
                self._llm_router = LLMQuestionRouter()
            route = self._llm_router.classify(question)
            return {"route": route, "method": "llm_fallback", "reason": "ambiguous — classified by LLM"}

        return {"route": "vector", "method": "default", "reason": "no graph signal — semantic/code search"}


class LLMQuestionRouter:
    """Tier 2 — เผื่ออัพเกรด: ใช้ LLM ตัดสิน route เมื่อ keyword ไม่ชัดเจน (ปิดไว้เป็นค่าเริ่มต้น)"""

    PROMPT = (
        "Classify this question as exactly one word: 'graph' or 'vector'.\n"
        "'graph': asks about call/dependency RELATIONSHIPS in the codebase (who calls what, what imports what).\n"
        "'vector': asks HOW a function/file works, general code explanation, or anything else.\n"
        "Respond with ONLY one word: graph or vector."
    )

    def classify(self, question: str) -> str:
        try:
            prompt = f"{self.PROMPT}\n\nQuestion: {question}\nAnswer:"
            raw = ollama_chat(prompt, temperature=0.0).strip().lower()
            if "graph" in raw:
                return "graph"
        except Exception as e:
            print(f"[LLMQuestionRouter] fallback to 'vector' after error: {e}")
        return "vector"


# ═════════════════════════════════════════════════════════════════════════════
#  Query functions
# ═════════════════════════════════════════════════════════════════════════════

def vector_query(vectorstore, question: str, k: int = TOP_K_CODE, model: str = MODEL_LLM) -> dict:
    docs = vectorstore.similarity_search(question, k=k)

    context_parts, sources = [], []
    for d in docs:
        func = d.metadata.get("function", "?")
        file = d.metadata.get("file", "?")
        line = d.metadata.get("line", "?")
        context_parts.append(f"# {func} in {file}\n{d.page_content}")
        sources.append({"file": file, "function": func, "line": line})
    context = "\n\n".join(context_parts)

    prompt = (
        "You are a coding assistant. Answer using the code context below. "
        "Be concise and reference the relevant function name.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    )
    answer = ollama_chat(prompt, model=model)
    return {"answer": answer, "mode": "vector", "sources": sources}


def graph_query(conn, question: str, model: str = MODEL_LLM) -> dict:
    func_name = extract_function_name(question)
    direction = detect_call_direction(question)

    if func_name:
        # จับชื่อเต็ม หรือท้ายชื่อหลังจุด (กัน 'send' ไปโดน 'resend')
        target = "a" if direction == "callees" else "b"
        result = conn.execute(
            f"MATCH (a:Function)-[:CALLS]->(b:Function) "
            f"WHERE {target}.name = $name OR {target}.name ENDS WITH $suffix "
            "RETURN a.name AS caller, b.name AS callee",
            {"name": func_name, "suffix": f".{func_name}"},
        )
    else:
        result = conn.execute(
            "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.file <> '' "
            "RETURN a.name AS caller, b.name AS callee LIMIT 20"
        )
    df = result.get_as_df()
    context = (f"Call relationships for '{func_name}':\n{df.to_string()}" if func_name else df.to_string())
    sources = df.to_dict(orient="records") if not df.empty else []

    prompt = (
        "Answer the code structure question using the graph data below. Be concise.\n\n"
        f"Graph data:\n{context}\n\nQuestion: {question}\nAnswer:"
    )
    answer = ollama_chat(prompt, model=model)
    return {"answer": answer, "mode": "graph", "sources": sources}


# ═════════════════════════════════════════════════════════════════════════════
#  HybridRAG — ประกอบทุกอย่างเข้าด้วยกัน (โหลดจาก index_metadata.json)
# ═════════════════════════════════════════════════════════════════════════════

class HybridRAG:
    def __init__(
        self,
        metadata: Optional[dict] = None,
        model: str = MODEL_LLM,
        enable_llm_router: bool = ENABLE_LLM_ROUTER_DEFAULT,
    ):
        self.model = model
        self.router = QuestionRouter(enable_llm_router=enable_llm_router)
        self.metadata = metadata or load_active_metadata()
        self.load_errors: dict[str, str] = {}

        self.vectorstore = None
        self.graph_conn = None

        if not self.metadata:
            self.load_errors["general"] = "ยังไม่เคย index โฟลเดอร์ไหนเลย — ไปหน้า Codebase Indexer ก่อน"
            return

        vector_db_path = self.metadata["vector_db_path"]
        graph_db_path = self.metadata["graph_db_path"]

        try:
            from langchain_ollama import OllamaEmbeddings
            from langchain_community.vectorstores import FAISS

            if Path(vector_db_path).exists():
                embeddings = OllamaEmbeddings(model=MODEL_EMBED_CODE)
                self.vectorstore = FAISS.load_local(vector_db_path, embeddings, allow_dangerous_deserialization=True)
            else:
                self.load_errors["vector"] = f"ไม่พบ {vector_db_path}/"
        except Exception as e:
            self.load_errors["vector"] = str(e)

        try:
            import kuzu

            if Path(graph_db_path).exists():
                db = kuzu.Database(graph_db_path)
                self.graph_conn = kuzu.Connection(db)
            else:
                self.load_errors["graph"] = f"ไม่พบ {graph_db_path}/"
        except Exception as e:
            self.load_errors["graph"] = str(e)

    def query(
        self,
        question: str,
        mode_override: Optional[str] = None,
        top_k: Optional[int] = None,
        verbose: bool = False,
    ) -> dict:
        start = time.perf_counter()

        if mode_override and mode_override != "auto":
            route, method, reason = mode_override, "manual_override", "user selected mode"
        else:
            route_info = self.router.classify(question)
            route, method, reason = route_info["route"], route_info["method"], route_info["reason"]

        if verbose:
            print(f"[Router] route={route} method={method} ({reason})")

        try:
            if route == "graph":
                if self.graph_conn is None:
                    raise RuntimeError(self.load_errors.get("graph", "graph DB ไม่พร้อมใช้งาน"))
                result = graph_query(self.graph_conn, question, model=self.model)
                # auto mode: graph หาไม่เจอ -> ลอง vector แทน (manual override ไม่ fallback)
                if not result["sources"] and method != "manual_override" and self.vectorstore is not None:
                    result = vector_query(self.vectorstore, question, k=top_k or TOP_K_CODE, model=self.model)
                    method += "+vector_fallback"
            else:
                if self.vectorstore is None:
                    raise RuntimeError(self.load_errors.get("vector", "vector DB ไม่พร้อมใช้งาน"))
                result = vector_query(self.vectorstore, question, k=top_k or TOP_K_CODE, model=self.model)
        except Exception as e:
            result = {"answer": f"เกิดข้อผิดพลาด: {e}", "mode": route, "sources": []}

        result["router_method"] = method
        result["router_reason"] = reason
        result["elapsed"] = round(time.perf_counter() - start, 2)
        return result


# ═════════════════════════════════════════════════════════════════════════════
#  CLI test
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("HybridRAG — CLI smoke test")
    print("=" * 60)

    meta = load_active_metadata()
    if not meta:
        print("ยังไม่ได้ index อะไรเลย — รัน index_folder('path/to/code') ก่อน หรือเปิดหน้า Codebase Indexer")
        sys.exit(0)

    print(f"Active index: {meta['basename']} ({meta['function_count']} functions, {meta['call_edge_count']} edges)")
    rag = HybridRAG(metadata=meta)

    test_questions = ["Who calls request?", "How does the Session class send requests?"]
    for q in test_questions:
        print(f"\nQ: {q}")
        result = rag.query(q, verbose=True)
        print(f"  Mode: {result['mode']} | {result['elapsed']}s")
        print(f"  Answer: {str(result['answer'])[:200]}")
