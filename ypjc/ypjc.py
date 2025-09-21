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

# --------------------------------------------------
# 页面配置
st.set_page_config(page_title="药品检查签名工具", layout="centered")
st.title("药品检查签名工具")

# 检查表按钮
if st.button("显示检查表"):
    if os.path.exists(NOTICE_MD):
        with open(NOTICE_MD, "r", encoding="utf-8") as f:
            st.markdown("### 📄 检查表")
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
# 生成 PDF
DATE_STR = datetime.now().strftime("%Y.%m.%d")

@st.cache_data(show_spinner=False)
def build_pdf(dept: str):
    if not os.path.exists(SRC):
        st.error("模板文件缺失"); st.stop()
    doc = fitz.open(SRC)
    if len(doc) < 2:
        st.error("模板页数不足"); st.stop()
    p1, p2 = doc[0], doc[1]
    # 注册中文字体
    if not any("song" in f for f in p1.get_fonts(full=False)):
        if not os.path.exists(FONT_PATH):
            st.error(f"字体文件不存在：{FONT_PATH}"); st.stop()
        p1.insert_font(fontname="song", fontfile=FONT_PATH)
    # 日期
    p1.insert_text((POS_DATE[0], POS_DATE[1]), DATE_STR, fontname="song", fontsize=10)

    # 科室
    if dept:
        if "song" not in [f[3] for f in p1.get_fonts(full=False)]:
            p1.insert_font(fontname="song", fontfile=FONT_PATH)
        p1.insert_text((POS_DEPT[0], POS_DEPT[1]), dept, fontname="song", fontsize=12)
    #扣分理由 
    if deduct_reason:
        if "song" not in [f[3] for f in p2.get_fonts(full=False)]:
            p2.insert_font(fontname="song", fontfile=FONT_PATH)
        x, y = POS_SCORE[0], POS_SCORE[1] + 60
        # 自动换行（宽度 420 pt，行高 18）
        p2.insert_textbox(fitz.Rect(x-100, y, x + 300, y + 80),
                          deduct_reason,
                          fontname="song", fontsize=11, align=0)
    # 插入图像
    insert_canvas_image(canvas_sig1, p2, POS_SIG1)
    insert_canvas_image(canvas_sig2, p2, POS_SIG2)
    insert_canvas_image(canvas_score, p2, POS_SCORE, size=(100, 50))

    out = io.BytesIO()
    doc.save(out, deflate=True,garbage=4)
    out.seek(0)
    return out

# --------------------------------------------------
# 下载管理
if "pdf_files" not in st.session_state:
    st.session_state.pdf_files = []

if st.button("生成 PDF"):
    pdf_bytes = build_pdf(dept_name)
    safe_dept = safe_filename(dept_name) or "未命名科室"
    filename = f"{OUT_PREFIX}_{safe_dept}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    st.session_state.pdf_files.append((filename, pdf_bytes.getvalue()))
    st.success(f"已生成：{filename}")
    if st.button("✅ 继续签名，下一科室"):
            # 只清空科室输入框，其余保留
            st.session_state.dept_key = str(datetime.now())   # 换 key 强制重置
            st.rerun()
# 4. 单文件下载（最近一个）
if st.session_state.pdf_files:
    latest_name, latest_data = st.session_state.pdf_files[-1]
    st.download_button(
        label="📄 下载当前PDF",
        data=latest_data,
        file_name=latest_name,
        mime="application/pdf"
    )
    st.warning("⚠️ 如需多次生成后统一打包，请保持本网页开启，不要刷新或点击rerun")
# 5. 打包下载全部
    if len(st.session_state.pdf_files) > 1:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for name, data in st.session_state.pdf_files:
                zf.writestr(name, data)
        zip_buf.seek(0)
        st.download_button(
            label="📦 打包下载全部 PDF",
            data=zip_buf,
            file_name=f"{OUT_PREFIX}_批量_{datetime.now():%Y%m%d_%H%M%S}.zip",
            mime="application/zip"
        )