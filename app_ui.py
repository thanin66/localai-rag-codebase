"""
app_ui.py — จุดเริ่มของ Local Coding Assistant (Chat + Codebase Indexer)
=========================================================================
รัน:
    uv run streamlit run app_ui.py
เปิดที่: http://localhost:8501

แถบด้านซ้ายมี 2 หน้า: Chat (ไฟล์นี้) และ Codebase Indexer (code_indexer.py)
ระบบเลือกเองว่าจะใช้ Vector หรือ Graph ในการตอบ (Router อัตโนมัติ)
ผู้ใช้บังคับ mode เองก็ได้จาก dropdown ใน sidebar (เผื่ออยากโชว์ตอนอัดคลิป)
"""

import sys

import streamlit as st

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import hybrid_rag as hr

st.set_page_config(page_title="Coding Assistant", page_icon="🤖", layout="wide")

MODE_LABELS = {
    "auto": "🧭 Auto (Router เลือกเอง)",
    "vector": "🔍 Vector",
    "graph": "🔗 Graph",
}
MODE_ICON = {"vector": "🔍", "graph": "🔗"}


def _format_source(src: dict, i: int) -> str:
    if "function" in src:
        return f"[{i}] {src.get('file', '?')}  ::  {src.get('function', '?')} (line {src.get('line', '?')})"
    if "caller" in src:
        return f"[{i}] {src.get('caller', '?')}  ->  {src.get('callee', '?')}"
    return f"[{i}] {src}"


# โหลด HybridRAG (cache ตาม path ของ index ปัจจุบัน — index เปลี่ยนแล้ว cache ก็เปลี่ยนตาม)
@st.cache_resource(show_spinner="กำลังโหลด RAG engine...")
def load_rag(vector_db_path: str, graph_db_path: str, model: str, enable_llm_router: bool) -> hr.HybridRAG:
    return hr.HybridRAG(metadata=hr.load_active_metadata(), model=model, enable_llm_router=enable_llm_router)


def chat_page() -> None:
    # Active index (เขียนโดยหน้า Codebase Indexer) — โหลดใหม่ทุก rerun เพราะไฟล์เล็กและอาจเพิ่งเปลี่ยน
    active_meta = hr.load_active_metadata()

    # ─── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🤖 Coding Assistant")
        if active_meta:
            st.caption(f"Ask about your indexed codebase (**{active_meta['basename']}**)")
            st.caption(
                f"{active_meta['function_count']} functions | "
                f"{active_meta['call_edge_count']} call edges | "
                f"{active_meta['file_count']} files"
            )
        else:
            st.warning("ยังไม่ได้ index โฟลเดอร์ไหนเลย — ไปหน้า **Codebase Indexer** ก่อน")

        with st.expander("⚙️ ตั้งค่า Local LLM", expanded=False):
            model_name = st.text_input("Generation model (Ollama)", value=hr.MODEL_LLM)
            st.caption(f"Embedding: `{hr.MODEL_EMBED_CODE}`")
            top_k = st.slider("Top-K (จำนวน chunk ที่ดึงมา — โหมด vector)", 1, 10, hr.TOP_K_CODE)

        mode_choice = st.selectbox("โหมดการค้นหา (Mode)", options=list(MODE_LABELS.keys()), format_func=lambda k: MODE_LABELS[k])

        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.session_state.query_count = 0
            st.session_state.total_elapsed = 0.0
            st.rerun()

        qc = st.session_state.get("query_count", 0)
        avg_t = (st.session_state.get("total_elapsed", 0.0) / qc) if qc else 0.0
        last = next((m for m in reversed(st.session_state.get("messages", [])) if m.get("mode")), None)
        # กล่องสถิติสไตล์เดียวกับ "Index ที่ใช้งานอยู่" ในหน้า Codebase Indexer
        with st.container(border=True):
            st.subheader("📊 Session Statistics")
            st.caption("สรุปการใช้งานในแชทนี้")
            t1, t2 = st.columns(2)
            t1.metric("Last answer", f"{last['elapsed']:.2f}s" if last else "–")
            t2.metric("Last mode", last["mode"].capitalize() if last else "–")
            b1, b2 = st.columns(2)
            b1.metric("Total", qc)
            b2.metric("Avg time", f"{avg_t:.2f}s" if qc else "–")

        if st.session_state.get("messages"):
            export_lines = ["# Coding Assistant — Conversation Export\n"]
            for m in st.session_state.messages:
                who = "**User**" if m["role"] == "user" else "**Assistant**"
                export_lines.append(f"{who}: {m['content']}\n")
                if m.get("mode"):
                    export_lines.append(f"> mode: {m['mode']} | {m.get('elapsed', '?')}s\n")
            st.download_button(
                "📥 Export conversation (.md)",
                data="\n".join(export_lines),
                file_name="conversation.md",
                mime="text/markdown",
            )

    if active_meta:
        rag = load_rag(active_meta["vector_db_path"], active_meta["graph_db_path"], model_name, hr.ENABLE_LLM_ROUTER_DEFAULT)
        if rag.load_errors:
            with st.sidebar:
                st.warning("บางส่วนยังไม่พร้อมใช้งาน:")
                for k, v in rag.load_errors.items():
                    st.caption(f"- **{k}**: {v}")
    else:
        rag = None

    # ─── Chat state + history ──────────────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "query_count" not in st.session_state:
        st.session_state.query_count = 0
    if "total_elapsed" not in st.session_state:
        st.session_state.total_elapsed = 0.0

    st.markdown("### ถามอะไรก็ได้เกี่ยวกับ codebase ที่ index ไว้ — ระบบจะเลือกเองว่าจะค้นแบบ Vector หรือ Graph")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("mode"):
                icon = MODE_ICON.get(msg["mode"], "🤖")
                st.caption(f"{icon} Mode: {msg['mode']} | {msg.get('elapsed', '?')}s | routed by: {msg.get('router_method', '?')}")
                if msg.get("sources"):
                    with st.expander(f"📎 Sources ({len(msg['sources'])})"):
                        for i, src in enumerate(msg["sources"], start=1):
                            st.code(_format_source(src, i))

    prompt = st.chat_input(
        "พิมพ์คำถาม เช่น 'How does the Session class work?' หรือ 'Who calls request?'",
        disabled=rag is None,
    )

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("กำลังค้นหาและตอบ..."):
                result = rag.query(prompt, mode_override=mode_choice, top_k=top_k, verbose=False)

            st.markdown(result["answer"])
            icon = MODE_ICON.get(result["mode"], "🤖")
            st.caption(f"{icon} Mode: {result['mode']} | {result['elapsed']}s | routed by: {result['router_method']}")

            sources = result.get("sources") or []
            if sources:
                with st.expander(f"📎 Sources ({len(sources)})"):
                    for i, src in enumerate(sources, start=1):
                        st.code(_format_source(src, i))

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result["answer"],
                "mode": result["mode"],
                "elapsed": result["elapsed"],
                "router_method": result["router_method"],
                "sources": sources,
            }
        )
        st.session_state.query_count += 1
        st.session_state.total_elapsed += result["elapsed"]
        # sidebar (Session Statistics / Export) ถูกวาดไปก่อนได้คำตอบ -> rerun ให้แสดงค่าล่าสุดทันที
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Navigation (แถบด้านซ้าย): Chat / Codebase Indexer
# ─────────────────────────────────────────────────────────────────────────────
nav = st.navigation(
    [
        st.Page(chat_page, title="Chat", url_path="chat", default=True),
        st.Page("code_indexer.py", title="Codebase Indexer", url_path="indexer"),
    ]
)
nav.run()
