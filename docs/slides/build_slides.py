"""Build the presentation deck (docs/slides/slides.pptx) with python-pptx.

    python docs/slides/build_slides.py [--results results/ablation_results.csv] [--data data/voicebank_demand_16k]

* If ``results/ablation_results.csv`` exists (``scripts/collect_results.py``), the result
  table and chart are filled in automatically; otherwise they show "pending" placeholders.
* If VoiceBank-DEMAND is available, the spectrogram figure uses a real test utterance
  (and the baseline's enhanced output if ``runs/a00_baseline/eval/wavs`` exists);
  otherwise a synthetic illustration is drawn and labelled as such.
Export to PDF with ``export_pdf.ps1`` (PowerPoint) or LibreOffice.
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

import numpy as np
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------ palette
# "magma" palette: the colormap of the spectrograms in this project.
INK = "1A1423"      # dark background / main text
PLUM = "3D1E4F"
MAGENTA = "B5367A"
CORAL = "E8553F"
AMBER = "F5A524"
WHITE = "FFFFFF"
TINT = "F5F0F7"     # light card fill
LINE = "E2D9E6"
MUTED = "6B6275"
GOOD = "2E8B57"
HEAD = "Cambria"
BODY = "Calibri"

W, H = 13.333, 7.5


def rgb(hex_):
    return RGBColor.from_string(hex_)


# ------------------------------------------------------------------ helpers
def text(slide, x, y, w, h, content, size=16, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False, spacing=4, name=None):
    """content: str | list of paragraphs; a paragraph is str or list of (text, {opts}) runs.
    A paragraph str starting with '• ' becomes a bulleted line."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.02)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing)
        runs = para if isinstance(para, list) else [(para, {})]
        bullet = isinstance(para, str) and para.startswith("• ")
        if bullet:
            runs = [(para[2:], {})]
            _bullet(p)
        for t, opt in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = opt.get("font", font)
            f.size = Pt(opt.get("size", size))
            f.bold = opt.get("bold", bold)
            f.italic = opt.get("italic", italic)
            f.color.rgb = rgb(opt.get("color", color))
    return tb


def _bullet(p, char="•", color=MAGENTA):
    from pptx.oxml.ns import qn
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Emu(Inches(0.22))))
    pPr.set("indent", str(-Emu(Inches(0.22))))
    for tag in ("a:buClr", "a:buFont", "a:buChar", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    buClr = pPr.makeelement(qn("a:buClr"), {})
    clr = buClr.makeelement(qn("a:srgbClr"), {"val": color})
    buClr.append(clr)
    pPr.append(buClr)
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": char}))


def box(slide, x, y, w, h, fill=TINT, line=None, radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def badge(slide, x, y, label, fill=MAGENTA, d=0.5, size=16):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    c.fill.solid()
    c.fill.fore_color.rgb = rgb(fill)
    c.line.fill.background()
    c.shadow.inherit = False
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.size, r.font.bold, r.font.name = Pt(size), True, BODY
    r.font.color.rgb = rgb(WHITE)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return c


def arrow(slide, x1, y1, x2, y2, color=MUTED, width=1.75):
    a = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    a.line.color.rgb = rgb(color)
    a.line.width = Pt(width)
    from pptx.oxml.ns import qn
    ln = a.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)
    return a


def background(slide, color):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(color)


def title(slide, t, subtitle=None, dark=False):
    text(slide, 0.6, 0.38, W - 1.2, 0.8, t, size=34, bold=True, font=HEAD, color=WHITE if dark else INK,
         name="Title")
    if subtitle:
        text(slide, 0.6, 1.12, W - 1.2, 0.45, subtitle, size=16, color=AMBER if dark else MUTED, italic=True)


def footer(slide, n, dark=False):
    text(slide, 0.6, H - 0.42, 8, 0.3, "Tăng cường tiếng nói · Đồ án cuối kỳ · Xử lý tiếng nói", size=10,
         color="A79DB0" if dark else MUTED)
    text(slide, W - 1.4, H - 0.42, 0.8, 0.3, str(n), size=10, color="A79DB0" if dark else MUTED,
         align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, rows, col_w=None, size=12, header_fill=PLUM, row_h=0.36, highlight_rows=()):
    nr, nc = len(rows), len(rows[0])
    shp = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr))
    tbl = shp.table
    if col_w:
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Inches(cw)
    for r in range(nr):
        tbl.rows[r].height = Inches(row_h)
        for c in range(nc):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = rgb(header_fill)
            elif r in highlight_rows:
                cell.fill.fore_color.rgb = rgb("FBE3D6")
            else:
                cell.fill.fore_color.rgb = rgb(WHITE if r % 2 else TINT)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if c < 2 or not _numeric(rows[r][c]) else PP_ALIGN.CENTER
            run = p.add_run()
            run.text = str(rows[r][c])
            run.font.size = Pt(size)
            run.font.name = BODY
            run.font.bold = r == 0
            run.font.color.rgb = rgb(WHITE if r == 0 else INK)
    return shp


def _numeric(s):
    try:
        float(str(s).replace("−", "-").replace("+", ""))
        return True
    except ValueError:
        return str(s) in {"–", "-", "TBD"}


def bar_chart(slide, x, y, w, h, cats, vals, title_txt, colors=None, vmin=None, vmax=None, fmt='0.00'):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("PESQ", vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = title_txt
    tp = ch.chart_title.text_frame.paragraphs[0]
    tp.runs[0].font.size, tp.runs[0].font.bold = Pt(14), True
    tp.runs[0].font.name = BODY
    tp.runs[0].font.color.rgb = rgb(INK)
    plot = ch.plots[0]
    plot.gap_width = 45
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format, dl.number_format_is_linked = fmt, False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size, dl.font.name = Pt(12), BODY
    dl.font.color.rgb = rgb(INK)
    va = ch.value_axis
    if vmin is not None:
        va.minimum_scale = vmin
    if vmax is not None:
        va.maximum_scale = vmax
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb(LINE)
    va.tick_labels.font.size, va.tick_labels.font.name = Pt(11), BODY
    va.tick_labels.font.color.rgb = rgb(MUTED)
    va.format.line.fill.background()
    ca = ch.category_axis
    ca.tick_labels.font.size, ca.tick_labels.font.name = Pt(12), BODY
    ca.tick_labels.font.color.rgb = rgb(INK)
    ca.format.line.color.rgb = rgb(LINE)
    ca.reverse_order = True
    ser = plot.series[0]
    for i, _ in enumerate(vals):
        pt = ser.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb((colors or [MAGENTA] * len(vals))[i])
    return gf


def line_chart(slide, x, y, w, h, xs, ys, title_txt):
    cd = CategoryChartData()
    cd.categories = xs
    cd.add_series("PCS gain", ys)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = title_txt
    r = ch.chart_title.text_frame.paragraphs[0].runs[0]
    r.font.size, r.font.bold, r.font.name = Pt(13), True, BODY
    r.font.color.rgb = rgb(INK)
    s = ch.plots[0].series[0]
    s.format.line.color.rgb = rgb(CORAL)
    s.format.line.width = Pt(2.5)
    s.smooth = False
    from pptx.enum.chart import XL_MARKER_STYLE
    s.marker.style = XL_MARKER_STYLE.NONE
    va = ch.value_axis
    va.minimum_scale, va.maximum_scale = 0.9, 1.5
    va.major_gridlines.format.line.color.rgb = rgb(LINE)
    va.tick_labels.font.size = Pt(10)
    va.tick_labels.font.color.rgb = rgb(MUTED)
    va.tick_labels.number_format, va.tick_labels.number_format_is_linked = "0.0", False
    ca = ch.category_axis
    ca.tick_labels.font.size = Pt(10)
    ca.tick_labels.font.color.rgb = rgb(MUTED)
    ca.tick_label_position  # noqa: B018
    from pptx.oxml.ns import qn
    # show every 25th category label (kHz ticks)
    cax = ca._element
    for tag, val in (("c:tickLblSkip", "25"), ("c:tickMarkSkip", "25")):
        el = cax.makeelement(qn(tag), {"val": val})
        cax.append(el)
    return gf


# ------------------------------------------------------------- spectrogram
def spectrogram_png(data_root: Path | None) -> tuple[bytes, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sr = 16000
    panels, caption = None, ""
    if data_root and (data_root / "clean_testset_wav" / "p232_001.wav").exists():
        import soundfile as sf
        clean, _ = sf.read(data_root / "clean_testset_wav" / "p232_001.wav")
        noisy, _ = sf.read(data_root / "noisy_testset_wav" / "p232_001.wav")
        panels = [("Nhiễu", noisy), ("Sạch", clean)]
        enh = ROOT / "runs" / "a00_baseline" / "eval" / "wavs" / "p232_001.wav"
        if enh.exists():
            e, _ = sf.read(enh)
            panels.insert(1, ("Tăng cường (của nhóm)", e))
        caption = "Câu test p232_001 trong VoiceBank-DEMAND"
    else:
        rng = np.random.default_rng(3)
        t = np.arange(int(2.2 * sr)) / sr
        f0 = 140 + 25 * np.sin(2 * np.pi * 1.3 * t)
        ph = 2 * np.pi * np.cumsum(f0) / sr
        env = np.clip(np.sin(2 * np.pi * 2.2 * t) + 0.3, 0, None)
        clean = sum(np.sin(k * ph) / k for k in range(1, 25)) * env * 0.1
        babble = np.convolve(rng.standard_normal(len(t)), np.ones(6) / 6, "same")
        noisy = clean + 0.05 * babble + 0.02 * np.sin(2 * np.pi * 50 * t)
        panels = [("Nhiễu", noisy), ("Sạch", clean)]
        caption = "Minh họa (tín hiệu tổng hợp)"
    fig, axes = plt.subplots(1, len(panels), figsize=(4.1 * len(panels), 2.9), sharey=True)
    for ax, (name, x) in zip(np.atleast_1d(axes), panels):
        ax.specgram(np.asarray(x) + 1e-9, NFFT=400, Fs=sr, noverlap=300, cmap="magma", vmin=-130)
        ax.set_title(name, fontsize=12)
        ax.set_xlabel("thời gian (s)")
        ax.set_ylim(0, 8000)
    np.atleast_1d(axes)[0].set_ylabel("Hz")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    return buf.getvalue(), caption


# ---------------------------------------------------------------- results
def load_results(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows or None


def fnum(v, n=2):
    try:
        return f"{float(v):.{n}f}"
    except (TypeError, ValueError):
        return "–"


# ================================================================== slides
def build(out: Path, results_csv: Path, data_root: Path | None):
    import sys
    sys.path.insert(0, str(ROOT / "docs" / "report"))
    from make_figures import VI_DESC  # Vietnamese run labels shared with the report

    def vi(r):
        key = "noisy" if r["run"] == "noisy" else r["run"].split("_")[0]
        return VI_DESC.get(key, r.get("description", ""))

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    results = load_results(results_csv)
    n = 0

    def new(dark=False):
        nonlocal n
        n += 1
        s = prs.slides.add_slide(blank)
        background(s, INK if dark else WHITE)
        return s

    # 1 ── title ---------------------------------------------------------
    s = new(dark=True)
    text(s, 0.8, 1.6, 9.5, 0.5, "XỬ LÝ TIẾNG NÓI · ĐỒ ÁN CUỐI KỲ · HƯỚNG NGHIÊN CỨU", size=14, color=AMBER, bold=True)
    text(s, 0.8, 2.15, 11.5, 1.9, ["Tăng cường tiếng nói:", "khảo sát và nghiên cứu ablation MP-SENet"], size=42,
         bold=True, font=HEAD, color=WHITE, spacing=0)
    text(s, 0.8, 4.25, 11, 0.5, "Điều gì thực sự quan trọng trong một mô hình khử nhiễu biên độ–pha hiện đại?",
         size=20, italic=True, color="D9CFE0")
    text(s, 0.8, 5.25, 11.5, 1.2, ["Chau Kien Dat (25C15036)   ·   Nguyen Vi Khang (25C15043)",
                                   "Giảng viên: PGS.TS. Đinh Điền, TS. Châu Thành Đức",
                                   "Trường ĐH Khoa học Tự nhiên, ĐHQG-HCM · Chương trình Thạc sĩ · 2026"],
         size=14, color="A79DB0")
    for i, c in enumerate([PLUM, MAGENTA, CORAL, AMBER]):
        badge(s, 11.0 + 0.42 * i, 1.55, "", fill=c, d=0.3)
    s.notes_slide.notes_text_frame.text = (
        "Giới thiệu nhóm và đề tài: tăng cường tiếng nói một kênh. Chúng tôi khảo sát các công trình gần đây, xây dựng "
        "demo, cài đặt lại MP-SENet, chạy nghiên cứu ablation thay đổi từng yếu tố một và đề xuất hai cải tiến.")

    # 2 ── agenda --------------------------------------------------------
    s = new()
    title(s, "Nội dung", "Bốn phần của đồ án")
    items = [("1", "Khảo sát tài liệu", "6 bài báo 2023–2025, Q1 / A / A*: phương pháp, ưu và nhược điểm", "30%", PLUM),
             ("2", "Demo", "Làm sạch tiếng nói bằng mô hình đã huấn luyện, so với checkpoint chính thức", "20%", MAGENTA),
             ("3", "Nghiên cứu ablation", "4 ablation một yếu tố của MP-SENet trên VoiceBank-DEMAND", "30%", CORAL),
             ("4", "Phân tích & cải tiến", "Loss MR-STFT và perceptual contrast stretching (PCS)", "20%", AMBER)]
    for i, (k, h, d, pct, c) in enumerate(items):
        x = 0.6 + i * 3.08
        box(s, x, 1.95, 2.85, 4.3, fill=TINT)
        badge(s, x + 0.3, 2.25, k, fill=c, d=0.62, size=20)
        text(s, x + 0.3, 3.1, 2.35, 0.9, h, size=20, bold=True, font=HEAD)
        text(s, x + 0.3, 4.05, 2.35, 1.4, d, size=14, color=MUTED)
        text(s, x + 0.3, 5.45, 2.35, 0.6, pct, size=28, bold=True, color=c)
    footer(s, n)

    # 3 ── problem -------------------------------------------------------
    s = new()
    title(s, "Bài toán: khôi phục tiếng nói sạch từ tín hiệu nhiễu", "Tăng cường tiếng nói một kênh (monaural)")
    png, cap = spectrogram_png(data_root)
    s.shapes.add_picture(io.BytesIO(png), Inches(0.6), Inches(1.75), width=Inches(7.6))
    text(s, 0.6, 1.75 + 7.6 * 2.9 / 8.2 + 0.05, 7.6, 0.3, cap, size=10, color=MUTED, italic=True)
    box(s, 8.6, 1.75, 4.15, 1.25, fill=PLUM)
    text(s, 8.85, 1.85, 3.7, 1.05, [[("y(t) = s(t) + n(t)", {"size": 26, "bold": True, "color": WHITE, "font": HEAD})],
                                    [("ước lượng ŝ chỉ từ y (không có tín hiệu tham chiếu)", {"size": 13, "color": "E6DDEB"})]],
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 8.6, 3.25, 4.15, 2.0, [
        [("Tại sao quan trọng", {"bold": True, "size": 16})],
        "• Tiền xử lý cho ASR, nhận dạng người nói, máy trợ thính",
        "• Cuộc gọi & họp: nhiễu làm giảm độ dễ hiểu",
        "• Làm sạch dữ liệu TTS (ví dụ kho VLSP)"], size=14)
    text(s, 8.6, 5.15, 4.15, 1.6, [
        [("Đo lường thế nào (VoiceBank-DEMAND)", {"bold": True, "size": 16})],
        "• PESQ (1–4.5), STOI (0–1): chất lượng, độ dễ hiểu",
        "• CSIG / CBAK / COVL (1–5): dự đoán điểm MOS",
        "• SSNR, SI-SDR (dB): độ trung thực tín hiệu"], size=14)
    footer(s, n)
    s.notes_slide.notes_text_frame.text = (
        "Định nghĩa bài toán. Nhiễu lấp đầy khoảng trống giữa các hài trong spectrogram. Giới thiệu benchmark "
        "(VoiceBank-DEMAND: 11,572 cặp huấn luyện / 824 cặp test, 16 kHz) và các metric dùng trong mọi bài báo.")

    # 4 ── landscape -----------------------------------------------------
    s = new()
    title(s, "Thế giới giải quyết bài toán ra sao: ba nhóm", "2021 → 2025: từ mask đến mô hình sinh và language model")
    fams = [("Discriminative T-F", "Dự đoán mask / phổ từ STFT",
             ["MetricGAN+, CMGAN, MP-SENet", "SEMamba, DeepFilterNet"],
             "+ PESQ tốt nhất, ~2 M tham số, nhanh", "− có artefact, khó với pha, lệch miền", PLUM),
            ("Mô hình sinh: diffusion", "Học p(sạch | nhiễu), rồi lấy mẫu",
             ["SGMSE+, StoRM, DOSE"], "+ tự nhiên, bền với nhiễu chưa gặp",
             "− nhiều bước (chậm), ảo giác", MAGENTA),
            ("Language model / token", "Dự đoán token codec / SSL sạch bằng LM",
             ["SELM, MaskSR, GenSE"], "+ dữ liệu thực, nhiều loại méo",
             "− rất lớn, chậm, lệch nội dung / giọng", CORAL)]
    for i, (h, d, ex, pro, con, c) in enumerate(fams):
        x = 0.6 + i * 4.1
        box(s, x, 1.8, 3.85, 4.15, fill=TINT)
        badge(s, x + 0.3, 2.05, str(i + 1), fill=c, d=0.55, size=18)
        text(s, x + 1.0, 2.07, 2.7, 0.55, h, size=19, bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 0.3, 2.8, 3.3, 0.7, d, size=14, color=MUTED, italic=True)
        text(s, x + 0.3, 3.5, 3.3, 0.9, ["• " + e for e in ex], size=14)
        text(s, x + 0.3, 4.55, 3.3, 1.3, [[(pro, {"color": GOOD, "bold": True})], [(con, {"color": CORAL, "bold": True})]],
             size=14)
    text(s, 0.6, 6.15, 12.1, 0.7, [[("Xu hướng: ", {"bold": True, "color": MAGENTA}),
                                    ("mô hình hóa pha tường minh · huấn luyện theo metric (PESQ) · mô hình chuỗi theo thời "
                                     "gian + tần số (Conformer → Mamba) · độ bền vững nhờ mô hình sinh · thiết kế thời gian "
                                     "thực", {})]],
         size=14)
    footer(s, n)

    # 5-8 ── papers ------------------------------------------------------
    papers = [
        ("CMGAN: Conformer-based Metric GAN", "Abdulatif, Cao, Yang · IEEE/ACM TASLP 2024 (Q1)",
         ["Dense encoder → 4 Conformer hai giai đoạn (thời gian, tần số)",
          "Decoder mask cho biên độ + decoder phức tinh chỉnh phần thực/ảo",
          "Discriminator MetricGAN học PESQ → generator tối đa hóa nó"],
         ["Kết quả mạnh chỉ với 1.83 M tham số", "TF-Conformer nắm ngữ cảnh xa theo thời gian & tần số",
          "Đánh giá kỹ: khử nhiễu, khử vang, siêu phân giải"],
         ["Pha chỉ được tinh chỉnh gián tiếp", "Attention bậc hai, không causal",
          "Tính PESQ trong vòng huấn luyện rất chậm"],
         ("3.41", "PESQ trên VB-D")),
        ("MP-SENet: biên độ & pha song song", "Lu, Ai, Ling · Interspeech 2023 (CORE A); bản mở rộng Neural Networks 2025",
         ["Cùng backbone, hai decoder song song: mask biên độ + pha tường minh",
          "Decoder pha dự đoán (r, i) → atan2 cho pha không bị quấn",
          "Loss anti-wrapping: pha tức thời, group delay, tần số tức thời"],
         ["SOTA trong các mô hình ~2 M tham số", "Ước lượng pha tường minh đầu tiên hiệu quả",
          "Mã nguồn + checkpoint chính thức"],
         ["6 thành phần loss, trọng số chọn tay", "Không causal; chỉ huấn luyện với nhiễu VB-D",
          "Metric GAN có thể overfit PESQ"],
         ("3.50", "PESQ trên VB-D")),
        ("SGMSE+ và StoRM: diffusion cho SE", "Richter et al. & Lemercier et al. · IEEE/ACM TASLP 2023 (Q1)",
         ["SGMSE+: SDE trôi từ sạch → nhiễu; đảo ngược bằng predictor–corrector",
          "Mạng score NCSN++ trong miền STFT phức",
          "StoRM: mô hình dự đoán trước, diffusion tái tạo chi tiết sau"],
         ["Đầu ra tự nhiên, tốt nhất trên dữ liệu lệch miền", "Cùng mô hình khử được vang",
          "StoRM: không có tiếng thở giả, ít bước hơn"],
         ["~60 lần gọi mạng / câu (SGMSE+)", "Ảo giác ở SNR thấp",
          "PESQ thấp hơn SOTA discriminative"],
         ("2.93", "PESQ trên VB-D (SGMSE+)")),
        ("DOSE và GenSE: sinh hiệu quả & dựa trên token", "Tai et al. · NeurIPS 2023 (A*) — Yao et al. · ICLR 2025 (A*)",
         ["DOSE: diffusion dropout + prior thích nghi → chỉ 2 bước lấy mẫu",
          "GenSE: SE như language modelling trên token ngữ nghĩa SSL + codec",
          "Phân cấp: nhiễu → ngữ nghĩa sạch → âm học, giữ âm sắc"],
         ["DOSE: diffusion nhanh, tổng quát hóa tốt", "GenSE: bền vững trên bản ghi thực",
          "Một mô hình cho nhiều loại méo"],
         ["PESQ thấp hơn mô hình discriminative", "GenSE: lớn, giải mã autoregressive",
          "Nguy cơ lệch nội dung / giọng"],
         ("2", "bước lấy mẫu (DOSE)")),
    ]
    for k, (h, venue, method, pros, cons, stat) in enumerate(papers):
        s = new()
        title(s, h, venue)
        box(s, 0.6, 1.8, 7.9, 2.05, fill=TINT)
        text(s, 0.85, 1.95, 7.4, 0.4, "Phương pháp", size=16, bold=True, color=MAGENTA)
        text(s, 0.85, 2.35, 7.4, 1.5, ["• " + m for m in method], size=15)
        box(s, 0.6, 4.05, 3.85, 2.6, fill=WHITE, line=LINE)
        text(s, 0.85, 4.2, 3.4, 0.4, "Ưu điểm", size=16, bold=True, color=GOOD)
        text(s, 0.85, 4.6, 3.4, 2.0, ["• " + p for p in pros], size=14)
        box(s, 4.65, 4.05, 3.85, 2.6, fill=WHITE, line=LINE)
        text(s, 4.9, 4.2, 3.4, 0.4, "Nhược điểm", size=16, bold=True, color=CORAL)
        text(s, 4.9, 4.6, 3.4, 2.0, ["• " + c for c in cons], size=14)
        box(s, 8.9, 1.8, 3.85, 4.85, fill=PLUM)
        text(s, 9.1, 2.6, 3.45, 1.5, stat[0], size=72, bold=True, font=HEAD, color=AMBER, align=PP_ALIGN.CENTER)
        text(s, 9.1, 4.1, 3.45, 0.5, stat[1], size=16, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, 9.1, 5.6, 3.45, 0.7, "theo số liệu tác giả công bố", size=12, italic=True, color="CDBFD6",
             align=PP_ALIGN.CENTER)
        footer(s, n)

    # 9 ── comparison ----------------------------------------------------
    s = new()
    title(s, "So sánh trên VoiceBank-DEMAND", "PESQ (wb) công bố — mô hình discriminative dẫn đầu trên metric intrusive")
    cats = ["Đầu vào nhiễu", "SGMSE+ (TASLP'23)", "MetricGAN+ (IS'21)", "CMGAN (TASLP'24)", "MP-SENet (IS'23)",
            "SEMamba + PCS (SLT'24)"]
    vals = [1.97, 2.93, 3.15, 3.41, 3.50, 3.69]
    bar_chart(s, 0.6, 1.7, 7.0, 4.9, cats, vals, "PESQ trên tập test VB-D (công bố)",
              colors=["B9AEC2", MAGENTA, PLUM, PLUM, CORAL, AMBER], vmin=1.0, vmax=4.0)
    rows = [["Mô hình", "Loại", "Tham số", "Bước"],
            ["MetricGAN+", "mask + metric GAN", "–", "1"],
            ["CMGAN", "biên độ + phức", "1.83 M", "1"],
            ["MP-SENet", "biên độ + pha", "2.05 M", "1"],
            ["SGMSE+", "diffusion", "~65 M", "~60"],
            ["DOSE", "diffusion", "–", "2"],
            ["GenSE", "LM trên token", "lớn", "AR"]]
    table(s, 7.9, 1.85, 4.85, rows, col_w=[1.35, 1.6, 0.95, 0.95], size=12, row_h=0.42, highlight_rows=(3,))
    text(s, 7.9, 5.0, 4.85, 1.5, ["Mô hình sinh có PESQ thấp hơn nhưng tổng quát hóa tốt hơn và nghe tự nhiên hơn.",
                                  "Chúng tôi chọn MP-SENet: chính xác nhất trên mỗi tham số, có mã nguồn chính thức, và "
                                  "là nền tảng của các công trình sau."],
         size=13, color=MUTED)
    footer(s, n)

    # 10 ── Vietnam ------------------------------------------------------
    s = new()
    title(s, "Tại Việt Nam: nhiễu được xử lý trong các bài toán khác", "Ít bài báo SE chuyên biệt ở Q1/Q2 hoặc A/A*")
    cards = [("ASR bền vững", "Huấn luyện ASR tiếng Việt với nhiễu tăng cường, ví dụ trộn 2,000 giờ nhiễu thực tế vào "
                              "kho 200 giờ (Tạp chí Khoa học, 2025)."),
             ("Làm sạch dữ liệu TTS", "Các hệ thống TTS tại VLSP 2020/2021 khử nhiễu bản ghi thu thập trước khi huấn luyện."),
             ("Khoảng trống còn mở", "Chưa có benchmark SE tiếng Việt công khai kiểu VB-D; ngôn ngữ có thanh điệu → sai "
                                     "lệch pha/cao độ quan trọng hơn.")]
    for i, (h, d) in enumerate(cards):
        y = 1.8 + i * 1.62
        box(s, 0.6, y, 7.6, 1.4, fill=TINT)
        badge(s, 0.85, y + 0.42, str(i + 1), fill=[PLUM, MAGENTA, CORAL][i], d=0.55, size=18)
        text(s, 1.65, y + 0.15, 6.35, 0.4, h, size=17, bold=True, font=HEAD)
        text(s, 1.65, y + 0.55, 6.35, 0.85, d, size=14, color=MUTED)
    box(s, 8.6, 1.8, 4.15, 4.64, fill=PLUM)
    text(s, 8.9, 2.05, 3.6, 4.2, [[("Cơ hội", {"bold": True, "size": 20, "color": AMBER, "font": HEAD})],
                                  [("Một mô hình nhỏ với pha tường minh như MP-SENet là ứng viên tốt làm khâu tiền xử lý "
                                    "cho các pipeline ASR / TTS tiếng Việt.", {"color": WHITE, "size": 15})],
                                  [("Bước tiếp theo: xây dựng tập nhiễu–sạch tiếng Việt (ví dụ VIVOS + DEMAND / MUSAN) "
                                    "và fine-tune.", {"color": "E6DDEB", "size": 15})]], spacing=12)
    footer(s, n)

    # 11 ── demo ---------------------------------------------------------
    s = new()
    title(s, "Demo: mô hình của chúng tôi và mô hình chính thức", "Mọi đầu ra được chấm bằng cùng một bộ metric")
    steps = [("Chuẩn bị", "prepare_vbd.py\n48 → 16 kHz"), ("Huấn luyện", "se.train\ncheckpoint best.pt"),
             ("Tăng cường", "se.enhance\nwav / thư mục"), ("Chấm điểm", "PESQ, STOI, CSIG…\nscore_dir.py"),
             ("Nghe thử", "demo.ipynb\ncác lần chạy")]
    for i, (h, d) in enumerate(steps):
        x = 0.6 + i * 2.5
        box(s, x, 1.9, 2.1, 1.75, fill=TINT)
        badge(s, x + 0.2, 2.05, str(i + 1), fill=[PLUM, MAGENTA, CORAL, AMBER, PLUM][i], d=0.45, size=15)
        text(s, x + 0.72, 2.05, 1.36, 0.45, h, size=15, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 0.2, 2.65, 1.8, 0.95, d, size=13, color=MUTED)
        if i < len(steps) - 1:
            arrow(s, x + 2.12, 2.78, x + 2.48, 2.78)
    code = ("python -m se.enhance --ckpt runs/a00_baseline/checkpoints/best.pt --input noisy.wav --output out/\n"
            "jupyter notebook notebooks/demo.ipynb   # nghe baseline so với các lần chạy ablation\n"
            "bash scripts/demo_official_mpsenet.sh data/voicebank_demand_16k   # checkpoint chính thức (tham chiếu)")
    box(s, 0.6, 4.0, 12.15, 1.45, fill=INK)
    text(s, 0.85, 4.12, 11.7, 1.25, code.split("\n"), size=13, font="Courier New", color="F3E9F7")
    text(s, 0.6, 5.7, 12.15, 0.9, [[("Trong video: ", {"bold": True, "color": MAGENTA}),
                                    ("làm sạch một câu test bằng baseline, phát cùng câu đó qua các checkpoint ablation, "
                                     "rồi so sánh spectrogram và PESQ / STOI.", {})]], size=15)
    footer(s, n)

    # 12 ── architecture -------------------------------------------------
    s = new()
    title(s, "Giải pháp được chọn: phân tích sâu MP-SENet", "Bản cài đặt lại có 2.047 M tham số (bài báo: 2.05 M)")
    box(s, 0.6, 3.1, 1.9, 1.3, fill=TINT)
    text(s, 0.7, 3.15, 1.7, 1.2, [[("STFT nhiễu", {"bold": True})], "|Y|^0.3 và ∠Y", "201 bin × T"], size=13,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 2.52, 3.75, 2.9, 3.75)
    box(s, 2.9, 3.0, 2.0, 1.5, fill=PLUM)
    text(s, 3.0, 3.05, 1.8, 1.4, [[("Dense encoder", {"bold": True, "color": WHITE})],
                                  [("DenseBlock giãn, tần số ↓2", {"color": "E6DDEB", "size": 12})]], size=14,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 4.92, 3.75, 5.3, 3.75)
    box(s, 5.3, 2.75, 2.5, 2.0, fill=MAGENTA)
    text(s, 5.4, 2.8, 2.3, 1.9, [[("4 × TS-Conformer", {"bold": True, "color": WHITE})],
                                 [("Conformer thời gian → Conformer tần số", {"color": "FCE7F1", "size": 12})],
                                 [("MHSA + conv + FFN", {"color": "FCE7F1", "size": 12})]], size=15,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 7.82, 3.4, 8.3, 2.5)
    arrow(s, 7.82, 4.1, 8.3, 5.0)
    box(s, 8.3, 1.85, 2.4, 1.3, fill=CORAL)
    text(s, 8.4, 1.9, 2.2, 1.2, [[("Decoder biên độ", {"bold": True, "color": WHITE})],
                                 [("mask = 2·σ(a_f · x) → mask·|Y|", {"color": WHITE, "size": 12})]], size=14,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    box(s, 8.3, 4.35, 2.4, 1.3, fill=AMBER)
    text(s, 8.4, 4.4, 2.2, 1.2, [[("Decoder pha", {"bold": True})],
                                 [("(r, i) → atan2(i, r)", {"size": 12})]], size=14, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 10.72, 2.5, 11.15, 3.4)
    arrow(s, 10.72, 5.0, 11.15, 4.1)
    box(s, 11.15, 3.1, 1.6, 1.3, fill=TINT)
    text(s, 11.2, 3.15, 1.5, 1.2, [[("iSTFT", {"bold": True})], "ŝ tăng cường"], size=14, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.6, 5.95, 12.15, 0.9, [[("Ý tưởng chính: ", {"bold": True, "color": MAGENTA}),
                                     ("pha được dự đoán tường minh và song song với biên độ. Dự đoán một cặp thực/ảo giả "
                                      "rồi lấy atan2 tránh phải hồi quy trực tiếp một góc bị quấn.", {})]],
         size=15)
    footer(s, n)

    # 13 ── losses -------------------------------------------------------
    s = new()
    title(s, "Sáu hàm mục tiêu huấn luyện", "L = 0.9 L_mag + 0.3 L_pha + 0.1 L_com + 0.2 L_time + 0.1 L_cons + 0.05 L_metric")
    losses = [("Biên độ (magnitude)", "MSE trên |S|^0.3 đã nén", "0.9"),
              ("Pha (anti-wrapping)", "IP + group delay + tần số góc tức thời; f(x)=|x − 2π·round(x/2π)|", "0.3"),
              ("Phức (complex)", "MSE trên phần thực / ảo đã nén", "0.1"),
              ("Thời gian (time)", "L1 trên dạng sóng", "0.2"),
              ("Nhất quán (consistency)", "STFT(iSTFT(Ŝ)) ≈ Ŝ", "0.1"),
              ("Metric GAN", "D học PESQ; G đẩy D(ŝ) → 1", "0.05")]
    for i, (h, d, wgt) in enumerate(losses):
        col, row = i % 2, i // 2
        x, y = 0.6 + col * 6.15, 1.85 + row * 1.5
        box(s, x, y, 5.95, 1.3, fill=TINT)
        badge(s, x + 0.25, y + 0.3, wgt, fill=[CORAL, AMBER, MAGENTA, PLUM, PLUM, MAGENTA][i], d=0.7, size=13)
        text(s, x + 1.15, y + 0.15, 4.6, 0.4, h, size=17, bold=True, font=HEAD)
        text(s, x + 1.15, y + 0.55, 4.6, 0.7, d, size=13, color=MUTED)
    text(s, 0.6, 6.4, 12.15, 0.5, "Câu hỏi: có cần cả sáu không? Thành phần nào tạo ra mức tăng PESQ, thành phần nào chỉ "
         "khớp theo metric?", size=14, italic=True, color=MAGENTA)
    footer(s, n)

    # 14 ── ablation design ---------------------------------------------
    s = new()
    title(s, "Thiết kế ablation: mỗi lần thay đổi một yếu tố", "Mỗi cấu hình kế thừa configs/base.yaml và đổi đúng một khóa")
    rows = [["ID", "Thay đổi", "Câu hỏi"],
            ["a01", "bỏ metric discriminator", "Tín hiệu huấn luyện: tăng thật hay overfit PESQ?"],
            ["a02", "bỏ các loss pha", "Pha: học được khi không có chúng?"],
            ["a03", "chỉ biên độ (pha nhiễu)", "Luận điểm chính: pha tường minh có đáng?"],
            ["a04", "BiLSTM thay cho Conformer", "Backbone: attention+conv so với recurrent"]]
    table(s, 0.6, 1.75, 8.3, rows, col_w=[0.75, 3.35, 4.2], size=14, row_h=0.5)
    box(s, 0.6, 4.4, 8.3, 2.08, fill=TINT)
    text(s, 0.85, 4.52, 7.9, 1.9,
         [[("Đã cài đặt, để lại cho hướng phát triển", {"bold": True, "size": 15, "color": MAGENTA})],
          [("a05 bỏ loss nhất quán · a06 bỏ loss thời gian + phức · a07 decoder ánh xạ phức · a08 không nén · "
            "a09 2 khối Conformer · a10 mask sigmoid thường · p03 P1 + P2", {"color": MUTED})],
          [("Mỗi thí nghiệm một file trong configs/ablation/; chạy bằng EXPERIMENTS=configs/experiments_full.txt",
            {"color": MUTED, "size": 12})]], size=13, spacing=6)
    box(s, 9.2, 1.75, 3.55, 4.73, fill=PLUM)
    text(s, 9.45, 1.95, 3.1, 4.4, [[("Quy trình", {"bold": True, "size": 20, "color": AMBER, "font": HEAD})],
                                   [("VB-D 16 kHz; tách p226 & p287 làm validation", {"color": WHITE})],
                                   [("Tập test (824) chỉ dùng một lần, cho kết quả cuối", {"color": WHITE})],
                                   [("Cùng seed, số epoch, quy tắc chọn (PESQ val tốt nhất)", {"color": WHITE})],
                                   [("PESQ, CSIG, CBAK, COVL, SSNR, STOI, SI-SDR, tham số, RTF", {"color": WHITE})],
                                   [("7 lần chạy × 5 epoch, một SLURM job array", {"color": "E6DDEB"})]], size=14,
         spacing=10)
    footer(s, n)

    # 15 ── results table -----------------------------------------------
    s = new()
    title(s, "Kết quả ablation trên tập test VoiceBank-DEMAND",
          "Trung bình trên 824 câu · Δ = thay đổi PESQ so với baseline đầy đủ (a00)")
    header = ["Lần chạy", "Mô tả", "PESQ", "ΔPESQ", "CSIG", "CBAK", "COVL", "STOI", "SI-SDR"]
    if results:
        base = next((r for r in results if r["run"] == "a00_baseline"), None)
        rows = [header]
        hl = []
        for r in results:
            dp = "–"
            if base and r["run"] != "noisy" and r.get("pesq"):
                dp = f"{float(r['pesq']) - float(base['pesq']):+.3f}"
            rows.append([r["run"].split("_")[0], vi(r)[:40], fnum(r["pesq"], 3), dp, fnum(r["csig"]),
                         fnum(r["cbak"]), fnum(r["covl"]), fnum(r["stoi"], 3), fnum(r["si_sdr"])])
            if r["run"] == "a00_baseline":
                hl.append(len(rows) - 1)
        rh = min(0.34, 4.9 / len(rows))
        table(s, 0.6, 1.7, 12.15, rows, col_w=[1.0, 4.15, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
              size=11 if len(rows) > 12 else 12, row_h=rh, highlight_rows=tuple(hl))
    else:
        names = ["noisy", "a00", "a01", "a02", "a03", "a04"]
        rows = [header] + [[nm, VI_DESC[nm], "TBD", "TBD", "TBD", "TBD", "TBD", "TBD", "TBD"] for nm in names]
        table(s, 0.6, 1.7, 12.15, rows, col_w=[1.0, 4.15, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], size=13, row_h=0.5,
              highlight_rows=(2,))
        text(s, 0.6, 6.45, 12.15, 0.4, "Đang chờ kết quả: các lần huấn luyện đang chạy trên cụm HPC. Chạy "
             "scripts/collect_results.py rồi build lại slide để điền bảng.", size=12, italic=True, color=CORAL)
    footer(s, n)

    # 16 ── results chart + discussion ------------------------------------
    s = new()
    title(s, "Thành phần nào quan trọng nhất?", "PESQ của từng lần chạy (baseline được làm nổi bật) và cách đọc")
    if results:
        rr = [r for r in results if r["run"] != "noisy" and r.get("pesq")]
        cats = [r["run"].split("_")[0] for r in rr]
        vals = [float(r["pesq"]) for r in rr]
        cols = [AMBER if r["run"].startswith("a00") else GOOD if r["run"].startswith("p") else PLUM for r in rr]
        bar_chart(s, 0.6, 1.65, 6.9, 5.2, cats, vals, "PESQ (wb) trên tập test", colors=cols,
                  vmin=round(min(vals) - 0.2, 1), vmax=round(max(vals) + 0.1, 1), fmt="0.000")
        base = next((r for r in rr if r["run"] == "a00_baseline"), None)
        if base:
            ab = sorted([r for r in rr if r["run"].startswith("a") and r is not base],
                        key=lambda r: float(r["pesq"]))
            worst = ab[:3]
            bullets = [f"• {r['run'].split('_')[0]} ({vi(r)[:32]}): "
                       f"{float(r['pesq']) - float(base['pesq']):+.3f} PESQ" for r in worst]
            heads = "Giảm nhiều nhất khi bỏ đi"
        else:
            bullets, heads = [], "Thảo luận"
    else:
        box(s, 0.6, 1.75, 6.9, 4.9, fill=TINT)
        text(s, 0.9, 3.6, 6.3, 1.2, [[("Biểu đồ sẽ xuất hiện sau khi chạy xong trên HPC", {"bold": True, "size": 18})],
                                     [("sinh từ results/ablation_results.csv", {"color": MUTED})]],
             size=15, align=PP_ALIGN.CENTER)
        heads = "Giả thuyết cần kiểm tra"
        bullets = ["• a03 (pha nhiễu) được kỳ vọng giảm nhiều nhất: pha tường minh là luận điểm cốt lõi",
                   "• a01 (không GAN): PESQ giảm nhưng SI-SDR có thể tăng; GAN tối ưu theo metric",
                   "• a02 (không loss pha): cùng a03, tách vai trò loss pha và decoder pha",
                   "• a04 (BiLSTM): PESQ gần bằng nhưng chậm hơn, kém hơn với ngữ cảnh dài"]
    text(s, 7.85, 1.75, 4.9, 0.5, heads, size=19, bold=True, font=HEAD, color=MAGENTA)
    text(s, 7.85, 2.3, 4.9, 3.0, bullets, size=14, spacing=8)
    box(s, 7.85, 5.35, 4.9, 1.3, fill=PLUM)
    text(s, 8.05, 5.42, 4.5, 1.15, "Ngân sách 5 epoch: coi ΔPESQ dưới ~0.05 là chưa kết luận; kiểm chứng bằng paired "
         "test trên per_file.csv và nghe đầu ra.", size=13, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    footer(s, n)

    # 17 ── proposals -----------------------------------------------------
    s = new()
    title(s, "Đề xuất cải tiến", "Cả hai chỉ thay đổi khâu huấn luyện: không tốn thêm chi phí suy luận")
    box(s, 0.6, 1.75, 5.9, 2.25, fill=TINT)
    badge(s, 0.85, 1.95, "P1", fill=CORAL, d=0.62, size=15)
    text(s, 1.65, 1.95, 4.7, 0.6, "Loss multi-resolution STFT", size=19, bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.85, 2.65, 5.45, 1.35, ["• Mọi loss trong bài báo dùng một STFT (cửa sổ 25 ms)",
                                     "• Thêm spectral convergence + log-mag L1 ở FFT 256 / 512 / 1024 điểm",
                                     "• Nhắm vào pre-echo và transient bị nhòe"], size=14)
    box(s, 0.6, 4.2, 5.9, 2.45, fill=TINT)
    badge(s, 0.85, 4.4, "P2", fill=AMBER, d=0.62, size=15)
    text(s, 1.65, 4.4, 4.7, 0.6, "Perceptual contrast stretching", size=19, bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.85, 5.1, 5.45, 1.5, ["• Làm sắc mục tiêu sạch: log1p|S| × g(f), g ∈ [1, 1.4]",
                                   "• Hệ số theo mức quan trọng của từng dải với độ dễ hiểu",
                                   "• SEMamba: +0.14 PESQ trên Mamba. Có hiệu quả với Conformer?"], size=14)
    sys.path.insert(0, str(ROOT / "src"))
    from se.utils.pcs import pcs400_gains  # same table the training code uses
    g = [round(float(v), 3) for v in pcs400_gains(201)]
    xs = [f"{k * 8 / 200:.0f} kHz" if k % 25 == 0 else "" for k in range(201)]
    line_chart(s, 6.85, 1.75, 5.9, 3.3, xs, g, "Hệ số PCS g(f) theo bin tần số")
    rows = [["Lần chạy", "Thay đổi", "PESQ"], ["p01", "+ loss MR-STFT", "TBD"], ["p02", "+ mục tiêu PCS", "TBD"]]
    if results:
        rmap = {r["run"].split("_")[0]: r for r in results}
        for row in rows[1:]:
            if row[0] in rmap:
                row[2] = fnum(rmap[row[0]]["pesq"], 3)
    table(s, 6.85, 5.25, 5.9, rows, col_w=[1.2, 3.2, 1.5], size=13, row_h=0.35)
    footer(s, n)

    # 18 ── repo ------------------------------------------------------------
    s = new()
    title(s, "Thiết kế để tái lập", "Cấu trúc repo AI tiêu chuẩn · mỗi giai đoạn một lệnh · sẵn sàng cho HPC")
    tree = ["se-ablation/",
            "├── configs/      base.yaml · ablation/a01…p03",
            "├── src/se/       data · models · losses · metrics",
            "│               train.py · evaluate.py · enhance.py",
            "├── scripts/      prepare_vbd · collect_results · demo",
            "├── slurm/        train · ablation_array · ddp",
            "├── notebooks/    demo.ipynb",
            "├── tests/        pytest: shapes, losses, metrics",
            "└── docs/         review · ablation design · slides"]
    box(s, 0.6, 1.75, 6.6, 4.9, fill=INK)
    text(s, 0.85, 1.95, 6.2, 4.6, tree, size=13, font="Courier New", color="F3E9F7", spacing=3)
    steps = [("Cài đặt", "pip install -e \".[dev]\" · pytest -q"),
             ("Dữ liệu", "python scripts/prepare_vbd.py --out data"),
             ("Huấn luyện tất cả", "sbatch --array=0-6%1 slurm/ablation_array.sbatch"),
             ("Báo cáo", "python scripts/collect_results.py"),
             ("Slide", "python docs/slides/build_slides.py")]
    for i, (h, d) in enumerate(steps):
        y = 1.75 + i * 0.99
        badge(s, 7.55, y + 0.12, str(i + 1), fill=[PLUM, MAGENTA, CORAL, AMBER, PLUM][i], d=0.5, size=15)
        text(s, 8.25, y, 4.5, 0.4, h, size=16, bold=True)
        text(s, 8.25, y + 0.38, 4.5, 0.5, d, size=12, font="Courier New", color=MUTED)
    footer(s, n)

    # 19 ── conclusion ------------------------------------------------------
    s = new(dark=True)
    text(s, 0.8, 0.8, 11, 0.8, "Kết luận & hướng phát triển", size=36, bold=True, font=HEAD, color=WHITE)
    cols = [("Đã làm", ["Khảo sát 6 bài báo gần đây thuộc 3 nhóm",
                        "Xây dựng demo làm sạch tiếng nói",
                        "Cài đặt lại MP-SENet (2.05 M tham số); 4 ablation chính",
                        "Đề xuất loss MR-STFT và mục tiêu PCS"]),
            ("Rút ra", ["Thành phần nào tạo ra hiệu năng (slide kết quả)",
                        "Đóng góp của mô hình hóa pha so với metric GAN",
                        "Độ chính xác so với chi phí của backbone TF"]),
            ("Tiếp theo", ["Chạy 6 ablation còn lại và kết hợp P1 + P2",
                           "Huấn luyện lâu hơn để so với số liệu công bố",
                           "Khối Mamba; phiên bản causal / streaming",
                           "Dữ liệu nhiễu–sạch tiếng Việt và fine-tune"])]
    for i, (h, b) in enumerate(cols):
        x = 0.8 + i * 4.0
        box(s, x, 2.0, 3.7, 4.3, fill=PLUM)
        text(s, x + 0.3, 2.2, 3.1, 0.5, h, size=20, bold=True, color=AMBER, font=HEAD)
        text(s, x + 0.3, 2.85, 3.1, 3.3, [[(t, {"color": WHITE})] for t in b], size=15, spacing=10)
    text(s, 0.8, 6.6, 11, 0.4, "Cảm ơn thầy và các bạn đã lắng nghe!", size=18, italic=True, color="D9CFE0")
    footer(s, n, dark=True)

    # 20 ── team -------------------------------------------------------------
    s = new()
    title(s, "Thành viên và phân công")
    rows = [["Thành viên", "MSHV", "Công việc", "Tỉ lệ"],
            ["Chau Kien Dat", "25C15036", "Khảo sát tài liệu, demo, slide, viết báo cáo", "50%"],
            ["Nguyen Vi Khang", "25C15043", "Cài đặt lại mô hình, chạy ablation trên HPC, đánh giá, video", "50%"]]
    table(s, 0.6, 1.9, 12.15, rows, col_w=[2.6, 2.0, 6.0, 1.55], size=15, row_h=0.6)
    footer(s, n)

    # 21 ── references -----------------------------------------------------
    s = new()
    title(s, "Tài liệu tham khảo")
    refs = ["[1] S. Abdulatif, R. Cao, B. Yang. CMGAN: Conformer-based metric-GAN for monaural speech enhancement. IEEE/ACM TASLP, 32, 2024.",
            "[2] Y.-X. Lu, Y. Ai, Z.-H. Ling. MP-SENet: A speech enhancement model with parallel denoising of magnitude and phase spectra. Interspeech 2023.",
            "[3] J. Richter, S. Welker, J.-M. Lemercier, B. Lay, T. Gerkmann. Speech enhancement and dereverberation with diffusion-based generative models. IEEE/ACM TASLP, 31, 2023.",
            "[4] J.-M. Lemercier, J. Richter, S. Welker, T. Gerkmann. StoRM: A diffusion-based stochastic regeneration model for speech enhancement and dereverberation. IEEE/ACM TASLP, 31, 2023.",
            "[5] W. Tai, Y. Lei, F. Zhou, G. Trajcevski, T. Zhong. DOSE: Diffusion dropout with adaptive prior for speech enhancement. NeurIPS 2023.",
            "[6] J. Yao et al. GenSE: Generative speech enhancement via language models using hierarchical modeling. ICLR 2025.",
            "[7] S.-W. Fu et al. MetricGAN+: An improved version of MetricGAN for speech enhancement. Interspeech 2021.",
            "[8] H. Schröter et al. DeepFilterNet: A low complexity speech enhancement framework for full-band audio based on deep filtering. ICASSP 2022.",
            "[9] R. Chao et al. An investigation of incorporating Mamba for speech enhancement. IEEE SLT 2024.",
            "[10] C. Valentini-Botinhao et al. Investigating RNN-based speech enhancement methods for noise-robust text-to-speech. SSW 2016.",
            "[11] Y. Hu, P. C. Loizou. Evaluation of objective quality measures for speech enhancement. IEEE TASLP, 16(1), 2008."]
    text(s, 0.6, 1.3, 12.15, 5.6, refs, size=13, spacing=7)
    footer(s, n)

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"[slides] {n} slides -> {out}  (results: {'filled' if results else 'pending'})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "ablation_results.csv"))
    ap.add_argument("--data", default=str(ROOT / "data" / "voicebank_demand_16k"))
    ap.add_argument("--out", default=str(Path(__file__).with_name("slides.pptx")))
    args = ap.parse_args()
    build(Path(args.out), Path(args.results), Path(args.data))


if __name__ == "__main__":
    main()
