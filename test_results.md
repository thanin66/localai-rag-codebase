# รายงานผลการทดสอบระบบสืบค้นและตอบคำถาม (QA System Test Results)

รายงานสรุปการทดสอบประสิทธิภาพของระบบตอบคำถามจากคลังโค้ด (Codebase QA System) โดยประมวลผลคำถามจากไฟล์ `test_questions.md` ร่วมกับดัชนีข้อมูลของโปรเจกต์ Click Framework (`sample_data/click_src/`) ผ่านกลไก **Automatic Router**

---

## 1. สรุปภาพรวมการทดสอบ (Executive Summary)

| ตัวชี้วัด (Metric) | ผลการทดสอบ (Result) | หมายเหตุ |
| :--- | :---: | :--- |
| **จำนวนคำถามทั้งหมด** | **20 ข้อ** | ภาษาอังกฤษ 10 ข้อ / ภาษาไทย 10 ข้อ |
| **จำนวนที่ตอบถูกต้อง (Passed)** | **19 ข้อ** | คิดเป็นอัตราความแม่นยำ **95.0%** |
| **จำนวนที่ตอบหลุดบริบท (Off-topic)** | **1 ข้อ** | ข้อ 13 (ภาษาไทย) |
| **เวลาประมวลผลเร็วที่สุด** | **2.34 วินาที** | ข้อ 16 และ 17 (Graph Mode) |
| **เวลาประมวลผลช้าที่สุด** | **11.24 วินาที** | ข้อ 13 (Vector Mode - Hallucination) |
| **เวลาประมวลผลเฉลี่ย** | **4.24 วินาที** | ประมวลผลรวมทุกคำถาม |

---

## 2. ตารางผลการทดสอบอย่างละเอียด (Detailed Test Matrix)

| # | ข้อความคำถาม (Test Question) | ภาษา | โหมดการทำงาน | เงื่อนไข Routing | เวลา | สถานะ |
| :-: | :--- | :-: | :-: | :-: | :-: | :-: |
| **1** | How does Command.invoke run a command's callback? | EN | `Vector` | `default` | 4.49s | ✅ ผ่าน |
| **2** | What does the option decorator in decorators.py do? | EN | `Vector` | `default` | 6.89s | ✅ ผ่าน |
| **3** | Explain how Context.exit works. | EN | `Vector` | `default` | 4.85s | ✅ ผ่าน |
| **4** | What does HelpFormatter.write_usage do? | EN | `Vector` | `default` | 2.72s | ✅ ผ่าน |
| **5** | Who calls invoke? | EN | `Graph` | `keyword_graph` | 3.61s | ✅ ผ่าน |
| **6** | What functions call parse_args? | EN | `Graph` | `keyword_graph` | 2.67s | ✅ ผ่าน |
| **7** | Which functions call make_context? | EN | `Graph` | `keyword_graph` | 2.49s | ✅ ผ่าน |
| **8** | What does Group.invoke call? | EN | `Graph` | `pattern_graph` | 2.91s | ✅ ผ่าน |
| **9** | เขียนฟังก์ชัน Python เช็คว่าจำนวนเต็มเป็นจำนวนเฉพาะหรือไม่ | TH | `Vector` | `codegen_hint` | 6.41s | ✅ ผ่าน |
| **10** | เขียนฟังก์ชัน Python สำหรับ retry HTTP request 3 ครั้ง | TH | `Vector` | `codegen_hint` | 3.78s | ✅ ผ่าน |
| **11** | Command.invoke รัน callback ของคำสั่งยังไง? | TH | `Vector` | `default` | 3.98s | ✅ ผ่าน |
| **12** | decorator option ใน decorators.py ทำอะไร? | TH | `Vector` | `default` | 3.63s | ✅ ผ่าน |
| **13** | อธิบายการทำงานของ Context.exit | TH | `Vector` | `default` | 11.24s | ⚠️ หลุดบริบท |
| **14** | HelpFormatter.write_usage ทำอะไร? | TH | `Vector` | `default` | 5.01s | ✅ ผ่าน |
| **15** | ใครเรียก invoke บ้าง? | TH | `Graph` | `keyword_graph` | 2.80s | ✅ ผ่าน |
| **16** | ฟังก์ชันไหนเรียก parse_args? | TH | `Graph` | `keyword_graph` | 2.34s | ✅ ผ่าน |
| **17** | ฟังก์ชันไหนเรียกใช้ make_context? | TH | `Graph` | `keyword_graph` | 2.34s | ✅ ผ่าน |
| **18** | Group.invoke เรียกอะไรบ้าง? | TH | `Graph` | `keyword_graph` | 2.73s | ✅ ผ่าน |
| **19** | Write a Python function to check if an integer is prime. | EN | `Vector` | `codegen_hint` | 4.61s | ✅ ผ่าน |
| **20** | Write a Python function to retry an HTTP request up to 3 times. | EN | `Vector` | `codegen_hint` | 4.00s | ✅ ผ่าน |

---

## 3. สรุปสถิติตามประเภทคำถามและจำแนกตามภาษา

### 3.1 จำแนกตามการทำงานของ Router (Routing Performance)

| กลุ่มคำถาม | โหมดที่ส่งไป | กฎที่ใช้ (Rule Triggered) | จำนวน | ความแม่นยำ |
| :--- | :-: | :-: | :-: | :-: |
| **คำถามเชิงอธิบายการทำงาน (How it works)** | `Vector` | `default` | 8 | 87.5% (7/8) |
| **คำถามความสัมพันธ์โครงสร้าง (Call Graph)** | `Graph` | `keyword_graph` / `pattern_graph` | 8 | 100.0% (8/8) |
| **คำถามสร้างโค้ดตัวอย่าง (Code Generation)** | `Vector` | `codegen_hint` | 4 | 100.0% (4/4) |

### 3.2 จำแนกตามภาษา (Language Performance)

| ภาษา | จำนวนคำถาม | เวลาประมวลผลเฉลี่ย | ความแม่นยำ (Accuracy) |
| :--- | :-: | :-: | :-: |
| **ภาษาอังกฤษ (English)** | 10 | 4.12s | **100.0%** (10/10) |
| **ภาษาไทย (Thai)** | 10 | 4.36s | **90.0%** (9/10) |

---

## 4. ข้อสังเกตเชิงเทคนิคและการวิเคราะห์ปัญหา (Technical Analysis)

1. **ระบบคัดแยกเส้นทาง (Automatic Routing System)**
   * สามารถตรวจจับรูปแบบภาษาทั้ง EN/TH และส่งต่อไปยัง Search Engine ที่เหมาะสมได้อย่างสมบูรณ์ โดยไม่ต้องสลับโหมดด้วยตนเอง
   * คำถามกลุ่มสร้างโค้ด (Codegen) ตรวจพบเงื่อนไข `codegen_hint` ถูกต้อง ทำให้ระบบข้ามการสืบค้นในคลังโค้ด Click และเข้าสู่การเขียนโค้ดตามโจทย์ทันที

2. **ความสอดคล้องของโหมด Graph Search (Graph Consistency)**
   * ผลลัพธ์การค้นหาความสัมพันธ์โครงสร้างโค้ดมีความเที่ยงตรงสูงมากระหว่างภาษาอังกฤษและภาษาไทย ตัวอย่างเช่น คำถามข้อ 5 (*"Who calls invoke?"*) และข้อ 15 (*"ใครเรียก invoke บ้าง?"*) สามารถดึงรายการฟังก์ชันผู้เรียก (Callers) ชุดเดียวกันได้อย่างแม่นยำ

3. **วิเคราะห์เคสที่ตอบผิดพลาด (Failure Case - Item #13)**
   * **ลักษณะปัญหา**: คำถาม *"อธิบายการทำงานของ Context.exit"* ภาษาไทย ถูกตอบเป็นความหมายของ Special Method `__exit__` ของ Context Manager ทั่วไปในภาษา Python แทนที่จะอธิบายเมธอด `Context.exit()` เฉพาะของ Click Framework (ต่างจากข้อ 3 ซึ่งเป็นภาษาอังกฤษและตอบได้ถูกต้อง)
   * **สาเหตุ**: เกิดอาการ General Knowledge Drift โดยตัวโมเดล LLM ใช้น้ำหนักจากความรู้ทั่วไปในตัวโมเดลมาตอบแทนการดึงบริบทจาก Vector Retrieval เมื่อเจอประโยคภาษาไทย ส่งผลให้เวลาประมวลผลสูงขึ้นเป็น **11.24 วินาที**

---

## 5. ข้อเสนอแนะเพื่อการพัฒนา (Recommendations)

* **เพิ่มความเข้มงวดของ Context Grounding**: ปรับแต่ง System Prompt ให้โมเดลยึดบริบทข้อมูลที่ค้นหาได้ (Retrieved Context) เป็นหลักมากกว่าความรู้ทั่วไป
* **ปรับปรุง Semantic Embedding ภาษาไทย**: เพิ่มน้ำหนักของ Technical Keyterms ภาษาอังกฤษ (เช่น ชื่อคลาสหรือฟังก์ชัน) เมื่อปรากฏร่วมกับคำถามภาษาไทย เพื่อไม่ให้หลุดบริบทในขั้นตอน Retrieval
