# Local Coding Assistant — Hybrid RAG (Vector + Graph)

Mini Project: ผู้ช่วยเขียนโค้ดที่ตอบคำถามโดยอาศัย RAG (ไม่ใช่ความเก่งของโมเดลเปล่าๆ) —
index codebase อะไรก็ได้ → ถามคำถาม → ระบบเลือกเองว่าจะค้นแบบ **Vector** (ความหมาย/แนวคิด)
หรือ **Graph** (ความสัมพันธ์ใครเรียกใคร) แล้วให้ LLM ขนาด 5-8B ตอบโดยอิงบริบทที่ดึงมา

## โครงสร้างโปรเจกต์

```
coding-assistant/
├── app_ui.py                 # จุดเริ่ม (รันไฟล์นี้) + หน้า Chat + navigation
├── code_indexer.py           # หน้า Codebase Indexer (สร้าง vector_db/ + graph_db/)
├── hybrid_rag.py             # core engine: AST parsing, FAISS, Kuzu, Router, HybridRAG class
├── sample_data/
│   └── click_src/            # ซอร์สโค้ดจริงของ `click` library — ใช้เป็นข้อมูลทดสอบ (ไม่ได้แนบมาใน repo นี้ ดึงเองด้วย pip)
├── test_questions.md         # ชุดคำถามทดสอบ (deliverable "ข้อมูลสำหรับทดสอบระบบ")
└── requirements.txt
```

หลัง index แล้วจะมีโฟลเดอร์เพิ่ม `<ชื่อโฟลเดอร์>_vector_db/` และ `<ชื่อโฟลเดอร์>_graph_db/`
กับไฟล์ `index_metadata.json` (บอกว่า index ไหน "active" อยู่ตอนนี้)

## วิธีติดตั้ง

```powershell
# 1) ติดตั้ง Ollama แล้วดึงโมเดล
ollama pull qwen2.5-coder:7b       # generation (5-8B ตามที่ต้องการ)
ollama pull nomic-embed-text        # embedding สำหรับโค้ด
ollama serve                        # เปิดค้างไว้ใน terminal แยก

# 2) ติดตั้ง dependencies
uv add streamlit langchain-ollama langchain-community langchain-core faiss-cpu kuzu pandas
# หรือถ้าใช้ pip:
pip install -r requirements.txt
```

## วิธีรัน

```powershell
uv run streamlit run app_ui.py
```

เปิดที่ `http://localhost:8501` แล้ว:

1. ไปหน้า **Codebase Indexer** (sidebar ซ้าย) → กด "Browse..." หรือพิมพ์ path เอง
   (ทดสอบเร็วๆ ได้ด้วยโค้ดของไลบรารีอะไรก็ได้ที่ติดตั้งไว้ เช่น `pip show click` แล้วชี้ไปที่ path นั้น — ดู `test_questions.md`) → กด "เริ่ม Indexing"
2. กลับไปหน้า **Chat** → พิมพ์คำถาม → ระบบเลือกเองว่าจะตอบแบบ Vector หรือ Graph
   (บังคับ mode เองได้จาก dropdown ใน sidebar ถ้าอยากโชว์เปรียบเทียบ)
3. ดู **Sources** ใต้คำตอบ (ไฟล์/ฟังก์ชันที่ดึงมา หรือ caller→callee)
4. กด **Clear Chat** เพื่อล้างประวัติ

## สถาปัตยกรรม

```
User question
     |
     v
QuestionRouter (keyword tier 1: graph keywords -> graph, มิฉะนั้น -> vector)
     |            (tier 2 = LLM fallback router: เผื่ออัพเกรด ปิดไว้เป็นค่าเริ่มต้น
     |             เปิดได้จาก checkbox ใน sidebar)
 ┌───┴───┐
 v       v
graph   vector
(Kuzu)  (FAISS, function-level chunk จาก AST)
     |
     v
qwen2.5-coder:7b (generate คำตอบสุดท้าย)
```

- **Indexing แยกจาก serving**: index ครั้งเดียว (ช้า, 1-2 นาที) แล้ว chat โหลดจาก disk (เร็ว, cache ด้วย `@st.cache_resource`)
- **Router ไม่ผูกกับโค้ดตัวอย่างเดียว**: index โฟลเดอร์ไหนก็ได้ ระบบ AST-parse หา function/class เอง
- **ข้อควรรู้ (ข้อจำกัดที่ทราบอยู่แล้ว)**: การ resolve ว่า `callee` ตัวไหนถูกเรียก ใช้การจับคู่ชื่อ (name matching)
  ไม่ได้ทำ full type resolution ถ้ามีหลายฟังก์ชันชื่อซ้ำกันในคนละไฟล์ อาจ resolve ผิดตัวได้บ้าง
  (ข้อจำกัดเดียวกับที่สอนไว้ใน slide Session 12 เรื่อง call graph แบบง่าย)

## เผื่ออัพเกรด (ยังไม่เปิดใช้เป็นค่าเริ่มต้น)

- **LLM Router (Tier 2)**: เปิดจาก checkbox ใน sidebar — ใช้ LLM ช่วยตัดสิน route แทน keyword ล้วนๆ
- **Streaming คำตอบ**: มี `ollama_chat_stream()` เตรียมไว้ใน `hybrid_rag.py` แล้ว ยังไม่ได้ต่อเข้า UI
