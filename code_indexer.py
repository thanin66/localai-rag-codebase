"""
code_indexer.py — หน้า Codebase Indexer (สร้าง vector_db/ + graph_db/)
=====================================================================
ถูกเรียกผ่าน st.navigation ใน app_ui.py (ไม่ต้องรันไฟล์นี้ตรงๆ)
เลือกโฟลเดอร์ผ่าน Windows Explorer (หรือพิมพ์ path เอง) แล้วกด "เริ่ม Indexing"
ระบบจะสร้าง <ชื่อโฟลเดอร์>_vector_db/ และ <ชื่อโฟลเดอร์>_graph_db/ ให้อัตโนมัติ
พร้อมอัปเดต index_metadata.json ให้หน้า Chat รู้ว่าตอนนี้ใช้ index ไหนอยู่
"""

from pathlib import Path

import streamlit as st

import hybrid_rag as hr


def _pick_folder_dialog() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory()
        root.destroy()
        if selected:
            st.session_state.picked_folder = selected
    except Exception as e:
        st.session_state.pick_error = f"เปิดหน้าต่างเลือกโฟลเดอร์ไม่ได้ ({e}) — พิมพ์ path เองแทนได้เลย"


if "picked_folder" not in st.session_state:
    st.session_state.picked_folder = ""

active_meta = hr.load_active_metadata()

# ─── Sidebar: สรุป index ที่ใช้งานอยู่ ──────────────────────────────────────────
with st.sidebar:
    st.title("Codebase Indexer")
    if active_meta:
        st.caption(f"Active index: **{active_meta['basename']}**")
        st.caption(f"Indexed at {active_meta['indexed_at']}")
        if st.button("🗑️ เคลียร์ index ล่าสุด", use_container_width=True):
            hr.clear_active_index()
            st.cache_resource.clear()  # กัน Chat ใช้ HybridRAG instance เก่าค้างอยู่
            st.session_state.picked_folder = ""
            st.rerun()
    else:
        st.caption("ยังไม่มี index ที่ใช้งานอยู่")

st.title("Codebase Indexer")
st.caption(
    "สร้าง FAISS vector store + Kuzu call graph จากโฟลเดอร์โค้ด Python — "
    "แต่ละโฟลเดอร์ได้ DB แยกของตัวเอง ไม่เขียนทับ index ของโฟลเดอร์อื่น"
)

left, right = st.columns([3, 2], gap="large")

# ─── ซ้าย: เลือกโฟลเดอร์ + เริ่ม index ──────────────────────────────────────────
with left:
    with st.container(border=True):
        st.subheader("1. เลือกโฟลเดอร์")
        path_col, btn_col = st.columns([4, 1], vertical_alignment="bottom")
        with btn_col:
            st.button("Browse...", on_click=_pick_folder_dialog, use_container_width=True)
        with path_col:
            st.text_input(
                "Path ของโฟลเดอร์โค้ด",
                key="picked_folder",
                placeholder=r"เช่น D:\Coding\my_project",
            )
        if err := st.session_state.pop("pick_error", None):
            st.warning(err)

        folder = st.session_state.picked_folder.strip()
        p = Path(folder) if folder else None
        py_files: list[Path] = []

        if not folder:
            st.info("กด Browse... เพื่อเลือกโฟลเดอร์ หรือพิมพ์ path เอง")
        elif not p.is_dir():
            st.error("ไม่พบโฟลเดอร์นี้ — เช็ค path อีกครั้ง")
        else:
            py_files = hr.find_python_files(str(p))
            if py_files:
                st.success(f"พบไฟล์ .py {len(py_files)} ไฟล์ (รวม subfolder)")
                with st.expander("ดูรายชื่อไฟล์"):
                    st.code("\n".join(str(f.relative_to(p)) for f in py_files), language=None)
            else:
                st.warning("ไม่พบไฟล์ .py ในโฟลเดอร์นี้")

    with st.container(border=True):
        st.subheader("2. สร้าง index")
        if p is not None and py_files:
            st.caption(f"ปลายทาง: `{p.name}_vector_db/` + `{p.name}_graph_db/`")
        start = st.button("เริ่ม Indexing", type="primary", disabled=not py_files, use_container_width=True)

        if start:
            status = st.status("กำลัง index...", expanded=True)
            try:
                new_meta = hr.index_folder(str(p), progress_cb=status.write)
                status.update(label="เสร็จแล้ว", state="complete", expanded=False)
                st.success(
                    f"Index สำเร็จ: {new_meta['function_count']} functions, "
                    f"{new_meta['call_edge_count']} call edges จาก {new_meta['file_count']} ไฟล์ — "
                    "ไปหน้า **Chat** เพื่อเริ่มถามได้เลย"
                )
                st.cache_resource.clear()  # กัน Chat ใช้ HybridRAG instance ของ index เก่าค้างอยู่
                active_meta = new_meta
            except Exception as e:
                status.update(label="ผิดพลาด", state="error")
                st.error(f"Index ไม่สำเร็จ: {e}")

# ─── ขวา: สถานะ index ปัจจุบัน ─────────────────────────────────────────────────
with right:
    with st.container(border=True):
        st.subheader("Index ที่ใช้งานอยู่")
        if active_meta:
            st.markdown(f"**{active_meta['basename']}**")
            st.caption(active_meta["source_dir"])
            m1, m2, m3 = st.columns(3)
            m1.metric("ไฟล์ .py", active_meta["file_count"])
            m2.metric("ฟังก์ชัน", active_meta["function_count"])
            m3.metric("Call edges", active_meta["call_edge_count"])
            st.caption(f"Indexed at: {active_meta['indexed_at']}")
            st.caption(f"vector_db: `{active_meta['vector_db_path']}/`")
            st.caption(f"graph_db: `{active_meta['graph_db_path']}/`")
        else:
            st.info("ยังไม่เคย index อะไรเลย")
