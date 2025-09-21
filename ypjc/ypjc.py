import io
import os
import re
import zipfile
from datetime import datetime
import streamlit as st
from streamlit_drawable_canvas import st_canvas
import fitz
from PIL import Image

# --------------------------------------------------
# 路径 & 常量
BASE_DIR   = os.path.dirname(__file__)
SRC        = os.path.join(BASE_DIR, "template.pdf")
FONT_PATH  = os.path.join(BASE_DIR, "fonts", "SimSun.ttf")
NOTICE_MD  = os.path.join(BASE_DIR, "table.md")
OUT_PREFIX = "药品检查表"

POS_DEPT  = (131, 118)
POS_DATE  = (671, 118)
POS_SIG1  = (262, 468)
POS_SIG2  = (80, 468)
POS_SCORE = (522, 468)

# --------------------------------------------------
# 工具函数
def safe_filename(name: str):
    return re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9()_\-]', '_', name).strip('_')

def insert_canvas_image(canvas, page, pos, size=(60, 30)):
    if canvas and canvas.image_data is not None:
        img = Image.fromarray(canvas.image_data.astype("uint8"), mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        x, y = pos
        w, h = size
        page.insert_image(fitz.Rect(x, y, x + w, y + h), stream=buf)

def pdf_to_png(pdf_bytes):
    doc = fitz.open("pdf", pdf_bytes)
    pages_im = []
    max_w = 0
    total_h = 0

    # 1. 逐页转 PIL
    for pg in doc:
        pix = pg.get_pixmap()
        im = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pages_im.append(im)
        max_w = max(max_w, im.width)
        total_h += im.height

    # 2. 拼长图
    long_img = Image.new("RGB", (max_w, total_h), (255, 255, 255))
    y = 0
    for im in pages_im:
        long_img.paste(im, (0, y))
        y += im.height

    # 3. 返回字节
    out = io.BytesIO()
    long_img.save(out, format="PNG")
    out.seek(0)
    return out
# --------------------------------------------------
# 页面配置
st.set_page_config(page_title="药品检查签名工具", layout="centered")
st.title("药品检查签名工具")

# 1. 内置 Markdown 展示
if st.button("📄 显示检查表"):
    if os.path.exists(NOTICE_MD):
        with open(NOTICE_MD, "r", encoding="utf-8") as f:
            st.markdown(f.read())
    else:
        st.info("table.md 未找到，已跳过检查表展示。")

# 2. 科室输入
st.subheader("科室（病区）名称")
dept_name = st.text_input("请输入科室（病区）名称：",key="dept")

st.subheader("扣分理由（文本）")
deduct_reason = st.text_input("请填写扣分理由：", key="deduct")
# 3. 手写区域
st.subheader("护士长姓名")
canvas_sig1 = st_canvas(stroke_width=4, stroke_color="black", background_color="white",
                        height=120, width=360, drawing_mode="freedraw", key="sig1")

st.subheader("检查人员签名")
canvas_sig2 = st_canvas(stroke_width=4, stroke_color="black", background_color="white",
                        height=120, width=360, drawing_mode="freedraw", key="sig2")

st.subheader("得分")
canvas_score = st_canvas(stroke_width=4, stroke_color="black", background_color="white",
                         height=90, width=270, drawing_mode="freedraw", key="score")

# --------------------------------------------------
def build_pdf(dept: str, deduct_reason: str, sig1_data, sig2_data, score_data):
    DATE_STR = datetime.now().strftime("%Y.%m.%d")
    if not os.path.exists(SRC):
        st.error("模板文件缺失"); st.stop()
    doc = fitz.open(SRC)
    if len(doc) < 2:
        st.error("模板页数不足"); st.stop()
    p1, p2 = doc[0], doc[1]

    # 注册字体（每页都要）
    if not any("song" in f for f in p1.get_fonts(full=False)):
        if not os.path.exists(FONT_PATH):
            st.error(f"字体文件不存在：{FONT_PATH}"); st.stop()
        p1.insert_font(fontname="song", fontfile=FONT_PATH)
    if not any("song" in f for f in p2.get_fonts(full=False)):
        p2.insert_font(fontname="song", fontfile=FONT_PATH)

    # 日期
    p1.insert_text((POS_DATE[0], POS_DATE[1]), DATE_STR, fontname="song", fontsize=10)
    # 科室
    if dept:
        p1.insert_text((POS_DEPT[0], POS_DEPT[1]), dept, fontname="song", fontsize=12)
    # 扣分理由
    if deduct_reason:
        x, y = POS_SCORE[0], POS_SCORE[1] + 60
        p2.insert_textbox(fitz.Rect(x-100, y, x + 300, y + 80),
                          deduct_reason,
                          fontname="song", fontsize=11, align=0)
    # 插入签名图
    insert_canvas_image(sig1_data, p2, POS_SIG1)
    insert_canvas_image(sig2_data, p2, POS_SIG2)
    insert_canvas_image(score_data, p2, POS_SCORE, size=(100, 50))

    out = io.BytesIO()
    doc.save(out, deflate=True)
    out.seek(0)
    return out

# --------------------------------------------------
# 下载管理
if "png_files" not in st.session_state:
    st.session_state.png_files = []

# 1. 主按钮：生成 PNG（后台自动生成 PDF→PNG）
if st.button("生成 PNG 图片"):
    sig1_data = canvas_sig1.image_data if canvas_sig1 and canvas_sig1.image_data is not None else None
    sig2_data = canvas_sig2.image_data if canvas_sig2 and canvas_sig2.image_data is not None else None
    score_data = canvas_score.image_data if canvas_score and canvas_score.image_data is not None else None

    pdf_bytes = build_pdf(dept_name, deduct_reason, sig1_data, sig2_data, score_data)
    png_bytes = pdf_to_png(pdf_bytes)
    safe_dept = safe_filename(dept_name) or "未命名科室"
    png_filename = f"{OUT_PREFIX}_{safe_dept}_{datetime.now():%Y%m%d_%H%M%S}.png"
    st.session_state.png_files.append((png_filename, png_bytes.getvalue()))
    st.success(f"已生成：{png_filename}")

# 2. 下一科室：清空除 sig2 外的所有输入 & 签名
if st.session_state.png_files:
    if st.button("✅ 已生成图片，下一科室"):
        st.session_state.dept_name = ""
        st.session_state.deduct_reason = ""
        # 只换需要清空的画布 key
        st.session_state.sig1_key = str(datetime.now())
        st.session_state.score_key = str(datetime.now())
        st.rerun()

# 3. 逐个下载（始终显示）
if st.session_state.png_files:
    st.markdown("---")
    st.write("📎 点击单独下载每张图片：")
    for name, data in st.session_state.png_files:
        st.download_button(
            label=f"🖼️ {name}",
            data=data,
            file_name=name,
            mime="image/png",
            key=name
        )

# 4. 批量下载（≥2 张时出现）
if len(st.session_state.png_files) >= 2:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in st.session_state.png_files:
            zf.writestr(name, data)
    zip_buf.seek(0)
    st.download_button(
        label="📦 批量下载全部 PNG 图片",
        data=zip_buf,
        file_name=f"{OUT_PREFIX}_批量_{datetime.now():%Y%m%d_%H%M%S}.zip",
        mime="application/zip"
    )


