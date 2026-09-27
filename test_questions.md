# ข้อมูลสำหรับทดสอบระบบ (Test Questions)

Codebase ตัวอย่างที่แนบมาด้วย: **`sample_data/click_src/`**
(ซอร์สโค้ดจริงของไลบรารี [`click`](https://github.com/pallets/click) — 17 ไฟล์ .py)
ใช้ path นี้ในหน้า **Codebase Indexer** เพื่อสร้าง `click_src_vector_db/` + `click_src_graph_db/` ก่อนเริ่มถามคำถามด้านล่าง

ระบบเลือก mode เอง (Router อัตโนมัติ) — ไม่ต้องเลือก mode ก็ตอบถูกทางอยู่แล้ว
แต่ในคลิปสาธิตแนะนำให้ยกตัวอย่างทั้งสองแบบให้เห็นชัด ตามชุดคำถามด้านล่าง

## กลุ่ม 1 — ควร route ไป **Vector** (ถามเรื่อง "โค้ดทำงานยังไง")

1. How does Command.invoke run a command's callback?
2. What does the option decorator in decorators.py do?
3. Explain how Context.exit works.
4. What does HelpFormatter.write_usage do?

ภาษาไทย:

1. Command.invoke รัน callback ของคำสั่งยังไง?
2. decorator option ใน decorators.py ทำอะไร?
3. อธิบายการทำงานของ Context.exit
4. HelpFormatter.write_usage ทำอะไร?

## กลุ่ม 2 — ควร route ไป **Graph** (ถามเรื่อง "ใครเรียกใคร / โครงสร้าง")

1. Who calls invoke?
2. What functions call parse_args?
3. Which functions call make_context?
4. What does Group.invoke call?

ภาษาไทย:

1. ใครเรียก invoke บ้าง?
2. ฟังก์ชันไหนเรียก parse_args?
3. ฟังก์ชันไหนเรียกใช้ make_context?
4. Group.invoke เรียกอะไรบ้าง?

## กลุ่ม 3 — เขียนโค้ดใหม่ (ไม่เกี่ยวกับ codebase ที่ index ไว้โดยตรง — เทสว่า router ไม่หลงไปทาง Graph/Vector โดยไม่จำเป็น)

### ไทยเวอร์ชั่น

1. เขียนฟังก์ชัน Python เช็คว่าจำนวนเต็มที่รับเข้ามาเป็นจำนวนเฉพาะหรือไม่
2. เขียนฟังก์ชัน Python สำหรับ retry การเรียก HTTP request ถ้า fail ให้ลองใหม่ 3 ครั้ง

### English version

1. Write a Python function to check whether an input integer is prime.
2. Write a Python function to retry an HTTP request up to 3 times if it fails.

## วิธีใช้ตอนอัดคลิป (ไม่เกิน 5 นาที)

1. เปิด `uv run streamlit run app_ui.py` โชว์หน้าแชท
2. ไปหน้า **Codebase Indexer** เลือกโฟลเดอร์ `sample_data/click_src` กด "เริ่ม Indexing" โชว์ progress
3. กลับมาหน้า **Chat** ถามคำถามกลุ่ม 1 (Vector) แล้วโชว์ Mode indicator + Sources ที่ดึงมา
4. ถามคำถามกลุ่ม 2 (Graph) โชว์ว่า Mode เปลี่ยนเป็น Graph เอง + Sources เป็น caller/callee
5. กด **Clear Chat** โชว์ว่าประวัติหายหมด
