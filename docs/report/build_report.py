"""Build the written report (docs/report/report.docx) with python-docx.

    python docs/report/build_report.py            # figures + report.docx
    powershell -ExecutionPolicy Bypass -File docs/report/export_pdf.ps1   # update TOC, export report.pdf

If results/ablation_results.csv exists (scripts/collect_results.py), the result tables,
the results figure and the per-run discussion are filled in automatically.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import make_figures  # noqa: E402

FIG = HERE / "figures"
INK, PLUM, MAGENTA, CORAL = "1A1423", "3D1E4F", "B5367A", "E8553F"
TINT, MUTED, LINE = "F5F0F7", "6B6275", "D9CFE0"
HEAD, BODY = "Cambria", "Calibri"


# =================================================================== helpers
class Report:
    def __init__(self):
        self.doc = Document()
        self.fig_no = 0
        self.tab_no = 0
        self._setup()

    # ---------------------------------------------------------- styles
    def _setup(self):
        d = self.doc
        sec = d.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.3)
        sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.2)
        st = d.styles
        normal = st["Normal"]
        normal.font.name, normal.font.size = BODY, Pt(11)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY)
        pf = normal.paragraph_format
        pf.space_after, pf.line_spacing = Pt(6), 1.15
        for name, size, color, before, after in [("Heading 1", 18, PLUM, 18, 8), ("Heading 2", 14, INK, 14, 6),
                                                 ("Heading 3", 12, MAGENTA, 10, 4), ("Title", 30, INK, 0, 6)]:
            s = st[name]
            s.font.name, s.font.size, s.font.bold = HEAD, Pt(size), True
            s.font.color.rgb = RGBColor.from_string(color)
            rpr = s.element.get_or_add_rPr()
            rf = rpr.find(qn("w:rFonts"))
            if rf is None:
                rf = OxmlElement("w:rFonts")
                rpr.append(rf)
            for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rf.set(qn(a), HEAD)
            for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                if rf.get(qn(a)) is not None:
                    del rf.attrib[qn(a)]
            s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(before), Pt(after)
            s.paragraph_format.keep_with_next = True
        for name in ("List Bullet", "List Number"):
            st[name].font.name, st[name].font.size = BODY, Pt(11)
            st[name].paragraph_format.space_after = Pt(3)
        cap = st["Caption"]
        cap.font.name, cap.font.size, cap.font.italic, cap.font.bold = BODY, Pt(9.5), True, False
        cap.font.color.rgb = RGBColor.from_string(MUTED)
        cap.paragraph_format.space_after = Pt(10)
        from docx.enum.style import WD_STYLE_TYPE
        for lvl, indent in ((1, 0.0), (2, 0.5)):
            ts = st.add_style(f"toc {lvl}", WD_STYLE_TYPE.PARAGRAPH)
            ts.element.set(qn("w:styleId"), f"TOC{lvl}")
            ts.base_style = normal
            ts.paragraph_format.space_after = Pt(2 if lvl == 2 else 3)
            ts.paragraph_format.space_before = Pt(4 if lvl == 1 else 0)
            ts.paragraph_format.left_indent = Cm(indent)
            ts.font.bold = lvl == 1
        self._footer()

    def _footer(self):
        footer = self.doc.sections[0].footer
        p = footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("Tăng cường tiếng nói: khảo sát và nghiên cứu ablation MP-SENet   ·   trang ")
        r.font.size, r.font.color.rgb = Pt(9), RGBColor.from_string(MUTED)
        self._field(p, "PAGE", size=9)

    @staticmethod
    def _field(p, instr, size=None):
        run = p.add_run()
        if size:
            run.font.size = Pt(size)
            run.font.color.rgb = RGBColor.from_string(MUTED)
        for tag, extra in (("w:fldChar", {"w:fldCharType": "begin"}), ("w:instrText", None),
                           ("w:fldChar", {"w:fldCharType": "separate"}), ("w:t", None),
                           ("w:fldChar", {"w:fldCharType": "end"})):
            el = OxmlElement(tag)
            if extra:
                for k, v in extra.items():
                    el.set(qn(k), v)
            if tag == "w:instrText":
                el.set(qn("xml:space"), "preserve")
                el.text = f" {instr} "
            if tag == "w:t":
                el.text = "1" if instr == "PAGE" else "Nhấp chuột phải → Update Field để tạo mục lục."
            run._r.append(el)

    # ---------------------------------------------------------- inline markup
    def _runs(self, p, text, size=None, color=None):
        """**bold**, *italic*, `code` inline markup; write a backslash before * for a literal asterisk."""
        text = text.replace("\\*", "\x00")
        for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)", text):
            if not part:
                continue
            part = part.replace("\x00", "*")
            if part.startswith("**"):
                r = p.add_run(part[2:-2])
                r.bold = True
            elif part.startswith("`"):
                r = p.add_run(part[1:-1])
                r.font.name = "Consolas"
                r.font.size = Pt((size or 11) - 1)
                r.font.color.rgb = RGBColor.from_string(MAGENTA)
                continue
            elif part.startswith("*"):
                r = p.add_run(part[1:-1])
                r.italic = True
            else:
                r = p.add_run(part)
            if size:
                r.font.size = Pt(size)
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
        return p

    # ---------------------------------------------------------- blocks
    def h1(self, t):
        self.doc.add_heading(t, level=1)

    def h2(self, t):
        self.doc.add_heading(t, level=2)

    def h3(self, t):
        self.doc.add_heading(t, level=3)

    def p(self, text, align=None, size=None, color=None, after=None):
        para = self._runs(self.doc.add_paragraph(), text, size, color)
        if align == "center":
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if after is not None:
            para.paragraph_format.space_after = Pt(after)
        return para

    def bullets(self, items, numbered=False):
        for it in items:
            self._runs(self.doc.add_paragraph(style="List Number" if numbered else "List Bullet"), it)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def figure(self, name, caption, width_cm=15.5):
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.keep_with_next = True
        para.paragraph_format.space_after = Pt(2)
        para.add_run().add_picture(str(FIG / name), width=Cm(width_cm))
        self.fig_no += 1
        c = self.doc.add_paragraph(style="Caption")
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._runs(c, f"**Hình {self.fig_no}.** {caption}")
        return self.fig_no

    def table(self, rows, widths_cm, caption=None, highlight=(), size=10, center_from=2, center_cols=None):
        if caption:
            self.tab_no += 1
            c = self.doc.add_paragraph(style="Caption")
            c.paragraph_format.keep_with_next = True
            c.paragraph_format.space_after = Pt(3)
            self._runs(c, f"**Bảng {self.tab_no}.** {caption}")
        t = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for i, row in enumerate(rows):
            tr = t.rows[i]
            if i == 0:  # repeat header row on page breaks
                trPr = tr._tr.get_or_add_trPr()
                h = OxmlElement("w:tblHeader")
                h.set(qn("w:val"), "true")
                trPr.append(h)
            cant = OxmlElement("w:cantSplit")
            tr._tr.get_or_add_trPr().append(cant)
            for j, val in enumerate(row):
                cell = tr.cells[j]
                cell.width = Cm(widths_cm[j])
                fill = PLUM if i == 0 else ("FBE3D6" if i in highlight else ("FFFFFF" if i % 2 else TINT))
                self._shade(cell, fill)
                cp = cell.paragraphs[0]
                cp.paragraph_format.space_after = Pt(1)
                cp.paragraph_format.space_before = Pt(1)
                cp.paragraph_format.line_spacing = 1.0
                if i > 0 and (j in center_cols if center_cols is not None else j >= center_from):
                    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._runs(cp, str(val), size=size, color="FFFFFF" if i == 0 else INK)
                if i == 0:
                    for r in cp.runs:
                        r.bold = True
        self._borders(t)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(4)
        return t

    def callout(self, title, text, fill=TINT):
        t = self.doc.add_table(rows=1, cols=1)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        cell = t.rows[0].cells[0]
        cell.width = Cm(16.4)
        self._shade(cell, fill)
        cp = cell.paragraphs[0]
        cp.paragraph_format.space_before = Pt(4)
        self._runs(cp, f"**{title}**", color=MAGENTA)
        items = text if isinstance(text, list) else [text]
        for it in items:
            q = cell.add_paragraph()
            q.paragraph_format.space_after = Pt(3)
            self._runs(q, it)
        self._borders(t, color=fill)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def code(self, lines):
        t = self.doc.add_table(rows=1, cols=1)
        cell = t.rows[0].cells[0]
        cell.width = Cm(16.4)
        self._shade(cell, "F3F0F5")
        first = True
        for ln in lines:
            q = cell.paragraphs[0] if first else cell.add_paragraph()
            first = False
            q.paragraph_format.space_after = Pt(0)
            q.paragraph_format.line_spacing = 1.0
            r = q.add_run(ln)
            r.font.name, r.font.size = "Consolas", Pt(9)
            r.font.color.rgb = RGBColor.from_string(INK)
        self._borders(t, color="E2D9E6")
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    @staticmethod
    def _shade(cell, fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

    @staticmethod
    def _borders(table, color=LINE):
        tblPr = table._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "4")
            e.set(qn("w:color"), color)
            b.append(e)
        tblPr.append(b)
        mar = OxmlElement("w:tblCellMar")
        for side, v in (("left", 90), ("right", 90), ("top", 30), ("bottom", 30)):
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:w"), str(v))
            e.set(qn("w:type"), "dxa")
            mar.append(e)
        tblPr.append(mar)

    def toc(self):
        para = self.doc.add_paragraph()
        self._field(para, 'TOC \\o "1-2" \\h \\z \\u')

    def save(self, path):
        self.doc.save(path)


# ================================================================== content
# ================================================================== content
def fnum(v, n=2):
    try:
        return f"{float(v):.{n}f}"
    except (TypeError, ValueError):
        return "–"


VI_DESC = make_figures.VI_DESC


def vi_desc(row):
    key = "noisy" if row["run"] == "noisy" else row["run"].split("_")[0]
    return VI_DESC.get(key, row.get("description", ""))


# Ablations we ran: one per main design idea of MP-SENet (training signal, phase, backbone).
ABLATIONS = [
    ("a01", "Bỏ metric discriminator (không GAN)", "Mức tăng PESQ là thật, hay mô hình chỉ đang “học tủ” theo metric?"),
    ("a02", "Bỏ các loss pha anti-wrapping", "Decoder pha có học được pha hữu ích khi không được giám sát trực tiếp?"),
    ("a03", "Decoder chỉ biên độ; dùng lại pha nhiễu", "Luận điểm chính của bài báo: ước lượng pha tường minh có đáng không?"),
    ("a04", "BiLSTM thay cho Conformer", "Attention + tích chập so với mô hình hồi quy (recurrent)"),
]
# Implemented and configured (configs/ablation/), but not run within our compute budget.
FUTURE_ABLATIONS = [
    ("a05", "Bỏ loss nhất quán STFT", "Phổ dự đoán có cần là một STFT hợp lệ không?"),
    ("a06", "Bỏ loss L1 miền thời gian và loss phức", "Các loss trên dạng sóng và miền phức có đóng góp gì?"),
    ("a07", "Một decoder ánh xạ trực tiếp ra phổ phức", "Biên độ + pha song song so với ánh xạ phức"),
    ("a08", "Không nén biên độ (c = 1)", "Nén dải động có giúp ích không?"),
    ("a09", "2 thay vì 4 khối TS-Conformer", "Cần độ sâu bao nhiêu? Chất lượng so với tốc độ"),
    ("a10", "Mask sigmoid thường (β = 1, độ dốc cố định)", "Cho mask khuếch đại (giá trị > 1) có giúp ích?"),
    ("p03", "Kết hợp P1 + P2", "Hai cải tiến đề xuất có cộng dồn hiệu quả?"),
]


def build(out_docx: Path, results_csv: Path, data_root: Path):
    rows = make_figures.make_all(results_csv, data_root)
    R = Report()

    # ------------------------------------------------------------ cover
    for _ in range(3):
        R.p("")
    R.p("XỬ LÝ TIẾNG NÓI · ĐỒ ÁN CUỐI KỲ · HƯỚNG NGHIÊN CỨU", size=11, color=MAGENTA, after=10)
    t = R.doc.add_paragraph(style="Title")
    t.add_run("Tăng cường tiếng nói")
    R.p("Tổng quan các phương pháp gần đây và nghiên cứu ablation trên MP-SENet", size=17, color=PLUM, after=28)
    R.p("Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM · Chương trình Thạc sĩ", size=11, color=MUTED, after=2)
    R.p("Giảng viên: PGS.TS. Đinh Điền, TS. Châu Thành Đức", size=11, color=MUTED, after=2)
    R.p(f"Tháng {date.today().month} năm {date.today().year}", size=11, color=MUTED, after=24)
    R.p("**Thành viên nhóm và phân công**", size=12, after=4)
    R.table([["Thành viên", "MSHV", "Công việc chính", "Tỉ lệ"],
             ["Chau Kien Dat", "25C15036", "Khảo sát tài liệu (Chương 3), demo (Chương 4), slide, viết báo cáo", "50%"],
             ["Nguyen Vi Khang", "25C15043", "Cài đặt lại mô hình, chạy ablation trên HPC, đánh giá (Chương 5–8), video", "50%"]],
            [3.4, 2.6, 8.4, 1.8], size=10.5, center_from=3)
    R.p("Mã nguồn và hướng dẫn dữ liệu: https://github.com/KhangNV0701/HCMUS-SpeechProcessing", size=10, color=MUTED)
    R.page_break()

    # ------------------------------------------------------------ TOC
    h = R.doc.add_paragraph()
    r = h.add_run("Mục lục")
    r.font.name, r.font.size, r.bold = HEAD, Pt(20), True
    r.font.color.rgb = RGBColor.from_string(PLUM)
    R.toc()
    R.page_break()

    # ------------------------------------------------------------ summary
    R.h1("Tóm tắt")
    R.p("**Tăng cường tiếng nói (speech enhancement)** là bài toán loại bỏ nhiễu nền khỏi bản ghi tiếng nói. "
        "Đồ án gồm bốn phần:")
    R.bullets([
        "**Khảo sát (Chương 3).** Chúng tôi đọc sáu bài báo gần đây ở các hội nghị/tạp chí hàng đầu (IEEE/ACM TASLP, "
        "Interspeech, NeurIPS, ICLR). Các phương pháp hiện nay chia thành ba nhóm: mô hình *discriminative* dự đoán phổ "
        "sạch trong một lần chạy, mô hình *diffusion* sinh tiếng nói sạch qua nhiều bước, và phương pháp dựa trên "
        "*language model* dự đoán các token âm thanh sạch.",
        "**Demo (Chương 4).** Demo dùng mô hình đã huấn luyện để làm sạch các bản ghi nhiễu trong tập test, cho nghe và "
        "so sánh spectrogram trước/sau; một script khác chạy checkpoint chính thức của tác giả MP-SENet để tham chiếu. "
        "Mọi đầu ra đều được chấm bằng cùng một bộ metric.",
        "**Nghiên cứu ablation (Chương 5–6).** Chúng tôi cài đặt lại MP-SENet (2.05 M tham số) và chạy bốn thí nghiệm, "
        "mỗi thí nghiệm bỏ hoặc thay đúng một thành phần chính, để biết phần nào thực sự quan trọng. Sáu ablation khác "
        "đã được cài đặt sẵn và để lại cho hướng phát triển.",
        "**Cải tiến (Chương 7).** Chúng tôi đề xuất hai thay đổi chỉ ở khâu huấn luyện, không tốn thêm chi phí suy "
        "luận: loss STFT đa phân giải (multi-resolution STFT) và perceptual contrast stretching (PCS) cho mục tiêu "
        "huấn luyện.",
    ])
    if rows:
        base = next((r for r in rows if r["run"] == "a00_baseline"), None)
        best = max((r for r in rows if r["run"] != "noisy" and r.get("pesq")), key=lambda r: float(r["pesq"]))
        noisy = next((r for r in rows if r["run"] == "noisy"), None)
        R.callout("Kết quả chính", [
            (f"Baseline của chúng tôi đạt **PESQ {fnum(base['pesq'], 3)}** trên tập test VoiceBank-DEMAND"
             + (f" (đầu vào nhiễu: {fnum(noisy['pesq'], 2)})." if noisy else ".")) if base else "",
            f"Lần chạy tốt nhất: **{best['run'].split('_')[0]}** ({vi_desc(best)}), PESQ {fnum(best['pesq'], 3)}."])
    else:
        R.callout("Trạng thái thí nghiệm",
                  "Toàn bộ mã nguồn, cấu hình và script chạy job đã sẵn sàng. Các bảng kết quả ở Chương 6 và 7 sẽ "
                  "được điền tự động khi các lần huấn luyện trên cụm HPC hoàn tất "
                  "(`python docs/report/build_report.py`).")

    # ------------------------------------------------------------ 1 intro
    R.h1("1  Giới thiệu")
    R.h2("1.1  Bài toán")
    R.p("Micro hiếm khi chỉ thu được giọng người nói. Tiếng xe cộ, quạt, người khác và tiếng vang của phòng đều bị trộn "
        "vào. **Tăng cường tiếng nói một kênh (single-channel speech enhancement)** cố gắng khôi phục tiếng nói sạch *s* "
        "từ bản ghi nhiễu *y = s + n*, chỉ dùng duy nhất bản ghi đó. Khi hệ thống hoạt động thực tế, không có tín hiệu "
        "sạch để tham chiếu.")
    R.figure("fig_spectrogram.png", "Spectrogram biểu diễn năng lượng theo thời gian (trục x) và tần số (trục y). Tiếng "
             "nói hiện ra thành các hài (harmonic) sáng xếp chồng; nhiễu lấp đầy khoảng trống giữa chúng. Tăng cường "
             "tiếng nói cần đưa hình bên trái về gần nhất có thể với hình bên phải.")
    R.p("Tại sao bài toán này quan trọng:")
    R.bullets(["**Giao tiếp:** gọi điện thoại và gọi video, máy trợ thính và thiết bị hỗ trợ nghe.",
               "**Tiền xử lý cho hệ thống khác:** nhận dạng tiếng nói (ASR), xác minh người nói và phát hiện từ khóa "
               "đều kém đi khi có nhiễu.",
               "**Làm sạch dữ liệu:** các kho dữ liệu text-to-speech (TTS) thu thập từ Internet thường bị nhiễu."])
    R.h2("1.2  Những gì chúng tôi đã làm")
    R.bullets(["Khảo sát các công trình gần đây và so sánh các phương pháp trên cùng một benchmark (Chương 3).",
               "Xây dựng demo làm sạch tiếng nói và so sánh với mô hình chính thức của MP-SENet (Chương 4).",
               "Cài đặt lại MP-SENet và giải thích từng thành phần một cách dễ hiểu (Chương 5).",
               "Thiết kế và chạy nghiên cứu ablation thay đổi từng yếu tố một (Chương 6).",
               "Đề xuất và thử nghiệm hai cải tiến (Chương 7).",
               "Đóng gói toàn bộ thành một repository có thể tái lập (Chương 8)."], numbered=True)

    # ------------------------------------------------------------ 2 background
    R.h1("2  Kiến thức nền tảng")
    R.h2("2.1  Từ dạng sóng đến spectrogram")
    R.p("Phần lớn hệ thống hiện đại làm việc trên **biến đổi Fourier thời gian ngắn (short-time Fourier transform, "
        "STFT)**. Tín hiệu được cắt thành các khung ngắn chồng lên nhau (ở đây dài 25 ms, mỗi lần dịch 6.25 ms). Mỗi "
        "khung được biến thành một phổ gồm **biên độ (magnitude)**, tức mỗi tần số to bao nhiêu, và **pha (phase)**, tức "
        "mỗi tần số đang ở vị trí nào trong chu kỳ. Ở 16 kHz với FFT 400 điểm, mỗi khung có 201 bin tần số. STFT ngược "
        "(iSTFT) biến spectrogram trở lại thành dạng sóng.")
    R.p("Các hệ thống cũ chỉ làm sạch biên độ và dùng lại pha nhiễu, vì pha trông như ngẫu nhiên và khó dự đoán. Các "
        "công trình mới hơn, trong đó có MP-SENet, cho thấy **ước lượng cả pha** mang lại chất lượng tốt hơn rõ rệt.")
    R.h2("2.2  Masking và mapping")
    R.bullets(["**Masking:** dự đoán cho mỗi bin thời gian–tần số một số trong khoảng 0 đến khoảng 1 rồi nhân với biên "
               "độ nhiễu. Các bin bị nhiễu lấn át sẽ nhận giá trị nhỏ.",
               "**Mapping:** dự đoán trực tiếp phổ sạch (biên độ, hoặc phần thực và phần ảo)."])
    R.h2("2.3  Đo chất lượng như thế nào")
    R.p("Tất cả bài báo trong báo cáo này dùng benchmark **VoiceBank-DEMAND**: 11,572 cặp nhiễu/sạch để huấn luyện từ "
        "28 người nói và 824 cặp test từ 2 người nói chưa gặp, trộn với nhiễu ghi âm thật ở SNR 0–15 dB (huấn luyện) và "
        "2.5–17.5 dB (test).")
    R.table([["Metric", "Khoảng giá trị", "Ý nghĩa"],
             ["PESQ (wide-band)", "1 – 4.5", "Chất lượng tiếng nói cảm nhận (ITU-T P.862.2). Con số chính của lĩnh vực."],
             ["STOI / ESTOI", "0 – 1", "Mức độ dễ hiểu (intelligibility) của tiếng nói."],
             ["CSIG", "1 – 5", "Điểm ý kiến dự đoán cho *méo tiếng nói*."],
             ["CBAK", "1 – 5", "Điểm ý kiến dự đoán cho *mức khó chịu của nhiễu nền*."],
             ["COVL", "1 – 5", "Chất lượng *tổng thể* dự đoán."],
             ["SSNR, SI-SDR", "dB", "Độ trung thực tín hiệu: dạng sóng gần với tín hiệu sạch đến đâu."]],
            [3.4, 2.4, 10.6], caption="Các metric khách quan dùng trong báo cáo (tất cả đều càng cao càng tốt).",
            center_cols=(1,))

    # ------------------------------------------------------------ 3 survey
    R.h1("3  Khảo sát tài liệu")
    R.h2("3.1  Bức tranh tổng thể")
    R.p(f"Các phương pháp công bố trong giai đoạn 2021–2025 chia thành ba nhóm (Hình {R.fig_no + 1}). Chúng đánh đổi giữa "
        "độ chính xác trên các metric chuẩn, độ bền vững trong điều kiện mới, và chi phí tính toán.")
    R.figure("fig_taxonomy.png", "Ba nhóm phương pháp tăng cường tiếng nói hiện đại, với các mô hình tiêu biểu cùng "
             "ưu điểm (+) và nhược điểm (−) chính.")
    R.figure("fig_timeline.png", "Dòng thời gian các bài báo được thảo luận trong chương này.", width_cm=15.5)
    R.p("Năm xu hướng nổi bật:")
    R.bullets(["**Mô hình hóa pha tường minh:** dự đoán trực tiếp pha, với các loss hiểu được hiện tượng quấn 2π.",
               "**Huấn luyện theo metric:** một mạng discriminator học dự đoán PESQ, và mạng tăng cường được huấn luyện "
               "để tối đa hóa giá trị đó.",
               "**Mô hình chuỗi theo cả thời gian và tần số:** Conformer nhìn theo cả hai trục của spectrogram, nay đang "
               "được thay bằng các mô hình state-space nhanh hơn (Mamba).",
               "**Độ bền vững nhờ mô hình sinh:** diffusion và language model tổng quát hóa tốt hơn với nhiễu chưa gặp.",
               "**Hiệu quả tính toán:** thiết kế thời gian thực, độ phức tạp thấp cho điện thoại và máy trợ thính "
               "(ví dụ DeepFilterNet)."])

    papers = [
        ("3.2  CMGAN: Conformer-based Metric GAN",
         "S. Abdulatif, R. Cao, B. Yang. IEEE/ACM Transactions on Audio, Speech, and Language Processing (TASLP), "
         "vol. 32, 2024. Tạp chí Q1; phiên bản ngắn tại Interspeech 2022.",
         "Một encoder tích chập dense được nối với bốn khối *two-stage Conformer*, mô hình hóa ngữ cảnh lần lượt theo "
         "thời gian rồi theo tần số. Tiếp theo là hai decoder: một decoder dự đoán mask biên độ, decoder còn lại tinh "
         "chỉnh phần thực và phần ảo. Một *metric discriminator* học dự đoán PESQ, và generator được huấn luyện để đẩy "
         "giá trị dự đoán đó lên.",
         "PESQ 3.41, CSIG 4.63, CBAK 3.94, COVL 4.12, STOI 0.96, chỉ với 1.83 M tham số.",
         ["Chất lượng rất tốt so với kích thước mô hình nhỏ.", "Conformer thời gian–tần số nắm bắt ngữ cảnh xa.",
          "Được đánh giá kỹ trên khử nhiễu, khử vang và siêu phân giải."],
         ["Pha chỉ được tinh chỉnh gián tiếp qua nhánh phức.",
          "Chi phí attention tăng bậc hai theo độ dài câu; không causal (chưa chạy thời gian thực được).",
          "Tính PESQ cho discriminator làm chậm quá trình huấn luyện."]),
        ("3.3  MP-SENet: khử nhiễu song song biên độ và pha",
         "Y.-X. Lu, Y. Ai, Z.-H. Ling. Interspeech 2023 (CORE A). Bản mở rộng đăng trên Neural Networks (2025).",
         "Giữ backbone giống CMGAN nhưng dùng **hai decoder song song**: một cho biên độ (dạng mask) và một **ước lượng "
         "pha tường minh**. Decoder pha dự đoán hai số cho mỗi bin rồi lấy góc bằng atan2, nên luôn cho ra một pha hợp "
         "lệ. Các loss *anti-wrapping* đặc biệt so sánh pha chính xác qua ranh giới 2π.",
         "PESQ 3.50, CSIG 4.73, CBAK 3.95, COVL 4.22, STOI 0.96, với khoảng 2.05 M tham số.",
         ["Kết quả tốt nhất trong các mô hình cùng kích thước tại thời điểm công bố.",
          "Mô hình đầu tiên ước lượng pha trực tiếp và ổn định.", "Mã nguồn và checkpoint chính thức được công khai."],
         ["Sáu thành phần loss với trọng số chọn thủ công; không rõ thành phần nào quan trọng (đây là điều ablation "
          "của chúng tôi kiểm tra).",
          "Không causal; chỉ huấn luyện trên các loại nhiễu của VoiceBank-DEMAND.", "Metric GAN có thể overfit theo PESQ."]),
        ("3.4  SGMSE+: diffusion dựa trên score cho tăng cường tiếng nói",
         "J. Richter, S. Welker, J.-M. Lemercier, B. Lay, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023. Tạp chí Q1.",
         "Một *mô hình diffusion* làm việc trong miền STFT phức. Khi huấn luyện, mô hình định nghĩa một quá trình dần dần "
         "đưa tiếng nói sạch về phía hỗn hợp nhiễu cộng nhiễu Gauss. Khi test, một mạng nơ-ron (NCSN++) chạy ngược quá "
         "trình này từng bước, có điều kiện theo đầu vào nhiễu.",
         "PESQ 2.93, ESTOI 0.87, SI-SDR 17.3 dB trên VoiceBank-DEMAND; tốt hơn rõ rệt so với mô hình discriminative khi "
         "test trên dữ liệu từ một kho khác.",
         ["Đầu ra tự nhiên và tổng quát hóa mạnh.", "Cùng framework cũng khử được tiếng vang."],
         ["Chậm: khoảng 60 lần chạy mạng cho mỗi câu với mạng khoảng 65 M tham số.",
          "Có thể “ảo giác” ra tiếng thở hoặc âm giống âm vị ở SNR thấp.",
          "PESQ thấp hơn các mô hình discriminative tốt nhất."]),
        ("3.5  StoRM: tái sinh ngẫu nhiên (stochastic regeneration)",
         "J.-M. Lemercier, J. Richter, S. Welker, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023. Tạp chí Q1.",
         "Kết hợp hai hướng: một mạng dự đoán (discriminative) tạo ước lượng ban đầu, sau đó một mô hình diffusion "
         "*tái sinh* các chi tiết nhỏ bắt đầu từ ước lượng đó thay vì từ nhiễu thuần.",
         "Chất lượng tương đương SGMSE+ với ít bước lấy mẫu hơn nhiều và ít lỗi sinh hơn.",
         ["Loại bỏ lỗi phát âm/tiếng thở giả của diffusion thuần.", "Lấy mẫu nhanh hơn nhiều so với SGMSE+."],
         ["Phải huấn luyện và chạy hai mạng.", "Vẫn chậm hơn một mô hình discriminative đơn lẻ."]),
        ("3.6  DOSE: diffusion dropout với prior thích nghi",
         "W. Tai, Y. Lei, F. Zhou, G. Trajcevski, T. Zhong. NeurIPS 2023 (CORE A*).",
         "Mô hình diffusion có điều kiện đôi khi bỏ qua đầu vào nhiễu. DOSE khắc phục bằng *diffusion dropout* khi huấn "
         "luyện, buộc mô hình dựa vào điều kiện, và một *prior thích nghi* bắt đầu lấy mẫu từ một ước lượng nhiễu thay "
         "vì nhiễu ngẫu nhiên. Chỉ cần hai bước lấy mẫu.",
         "Tăng cường dựa trên diffusion hiệu quả, tổng quát hóa tốt và có phân tích lý thuyết.",
         ["Rất ít bước lấy mẫu.", "Tận dụng tín hiệu điều kiện tốt hơn."],
         ["PESQ vẫn thấp hơn rõ so với state of the art discriminative.", "Khó tinh chỉnh hơn."]),
        ("3.7  GenSE: tăng cường tiếng nói như bài toán language modelling",
         "J. Yao, H. Liu, C. Chen, Y. Hu, E. S. Chng, L. Xie. ICLR 2025 (CORE A*).",
         "Tiếng nói được chuyển thành token rời rạc: token *ngữ nghĩa* từ một mô hình self-supervised và token *âm học* "
         "từ một neural codec. Một language model trước hết ánh xạ token ngữ nghĩa nhiễu sang token sạch, rồi sinh token "
         "âm học, dùng prompting để giữ giọng của người nói.",
         "Độ tự nhiên (DNSMOS) và độ giống người nói cao trên bản ghi thực tế.",
         ["Bền vững với nhiều loại méo.", "Một mô hình cho nhiều tác vụ."],
         ["Rất lớn và chậm (giải mã autoregressive).",
          "Có thể làm đổi từ hoặc đổi giọng; các metric intrusive như PESQ phạt điều này."]),
    ]
    for title, venue, method, result, pros, cons in papers:
        R.h2(title)
        R.p("*" + venue.replace("*", "\\*") + "*", color=MUTED)
        R.p(f"**Ý tưởng.** {method}")
        R.p(f"**Kết quả công bố.** {result}")
        R.table([["Ưu điểm", "Nhược điểm"]] + [[pros[i] if i < len(pros) else "", cons[i] if i < len(cons) else ""]
                                                for i in range(max(len(pros), len(cons)))],
                [8.2, 8.2], size=10, center_from=9)

    R.h2("3.8  Các công trình liên quan khác")
    R.bullets(["**MetricGAN+** (Fu et al., Interspeech 2021): bộ ước lượng mask BLSTM được huấn luyện cùng một "
               "discriminator học PESQ (PESQ 3.15). Đây là nguồn gốc của metric discriminator trong CMGAN và MP-SENet.",
               "**DeepFilterNet** (Schröter et al., ICASSP 2022, cùng các bản v2/v3): tăng cường full-band (48 kHz) "
               "thời gian thực bằng band gain kết hợp *deep filtering*; độ phức tạp rất thấp.",
               "**SEMamba** (Chao et al., IEEE SLT 2024): thay các Conformer của MP-SENet bằng khối Mamba, có chi phí "
               "tăng tuyến tính theo độ dài. Báo cáo PESQ 3.55, hoặc 3.69 khi dùng perceptual contrast stretching (PCS). "
               "PCS là động lực cho cải tiến thứ hai của chúng tôi."])
    R.h2("3.9  So sánh")
    R.figure("fig_reported_pesq.png", "PESQ do các tác giả công bố trên tập test VoiceBank-DEMAND. Mô hình "
             "discriminative dẫn đầu trên metric intrusive này; mô hình diffusion đánh đổi một phần PESQ lấy độ bền vững.",
             width_cm=14)
    R.table([["Mô hình", "Nơi công bố", "Nhóm", "PESQ", "CSIG", "CBAK", "COVL", "Tham số"],
             ["Đầu vào nhiễu", "–", "–", "1.97", "3.35", "2.44", "2.63", "–"],
             ["MetricGAN+", "Interspeech'21", "Discriminative", "3.15", "4.14", "3.16", "3.64", "–"],
             ["SGMSE+", "TASLP'23", "Diffusion", "2.93", "–", "–", "–", "~65 M"],
             ["CMGAN", "TASLP'24", "Discriminative", "3.41", "4.63", "3.94", "4.12", "1.83 M"],
             ["MP-SENet", "Interspeech'23", "Discriminative", "3.50", "4.73", "3.95", "4.22", "2.05 M"],
             ["SEMamba (+PCS)", "SLT'24", "Discriminative", "3.55 (3.69)", "–", "–", "–", "~2 M"]],
            [2.9, 2.6, 2.6, 2.0, 1.4, 1.4, 1.4, 1.6], highlight=(5,),
            caption="Kết quả công bố trên VoiceBank-DEMAND (\"–\" = không báo cáo trong thiết lập tương đương).",
            center_from=3)
    R.callout("Vì sao chọn MP-SENet", [
        "MP-SENet cho độ chính xác trên mỗi tham số tốt nhất trong các mô hình có mã nguồn công khai, kết hợp phần lớn "
        "xu hướng hiện nay (TF-Conformer, pha tường minh, metric GAN, loss đa miền), và các mô hình sau như SEMamba được "
        "xây dựng dựa trên nó. Vì vậy hiểu được thành phần nào của nó quan trọng có ích vượt ra ngoài riêng mô hình này."])
    R.h2("3.10  Tình hình tại Việt Nam")
    R.p("Chúng tôi tìm thấy rất ít bài báo chuyên về tăng cường tiếng nói của các nhóm Việt Nam trên tạp chí Q1/Q2 hoặc "
        "hội nghị A/A\\*. Nhiễu chủ yếu được xử lý *bên trong* các bài toán khác:")
    R.bullets(["**ASR bền vững:** ví dụ, một nghiên cứu năm 2025 trên *Tạp chí Khoa học* bổ sung 2,000 giờ nhiễu thực "
               "tế của Việt Nam vào kho huấn luyện 200 giờ ở sáu mức SNR và giảm tỉ lệ lỗi từ (WER) trên các tập test "
               "nhiễu.",
               "**Làm sạch dữ liệu TTS:** các hệ thống text-to-speech tại VLSP 2020/2021 khử nhiễu các bản ghi thu thập "
               "hoặc bị nhiễu trước khi huấn luyện.",
               "**Khoảng trống còn mở:** chưa có benchmark nhiễu/sạch tiếng Việt công khai tương đương VoiceBank-DEMAND. "
               "Vì tiếng Việt là ngôn ngữ có thanh điệu, sai lệch về cao độ và pha có thể ảnh hưởng đến độ dễ hiểu nhiều "
               "hơn so với tiếng Anh."])

    # ------------------------------------------------------------ 4 demo
    R.h1("4  Demo")
    R.p("Demo gồm ba phần. Mọi đầu ra đều được chấm bằng cùng một đoạn mã metric nên phép so sánh là công bằng.")
    R.bullets(["**Mô hình của chúng tôi:** `python -m se.enhance` làm sạch một file wav hoặc cả thư mục bằng một "
               "checkpoint đã huấn luyện (ví dụ baseline a00).",
               "**So sánh bằng tai nghe:** `notebooks/demo.ipynb` tăng cường một vài câu test bằng baseline và các "
               "checkpoint ablation, phát lại âm thanh, hiển thị spectrogram và metric cho từng câu. Một số hiệu ứng, như "
               "việc thiếu ước lượng pha, nghe thấy rõ hơn là đọc từ PESQ.",
               "**Mô hình chính thức (tham chiếu):** `scripts/demo_official_mpsenet.sh` tải mã nguồn và checkpoint "
               "VoiceBank-DEMAND đã huấn luyện sẵn của tác giả, tăng cường 824 file test và chấm điểm bằng metric của "
               "chúng tôi."])
    R.code(["python -m se.enhance --ckpt runs/a00_baseline/checkpoints/best.pt --input noisy.wav --output out/",
            "jupyter notebook notebooks/demo.ipynb",
            "bash scripts/demo_official_mpsenet.sh data/voicebank_demand_16k"])

    # ------------------------------------------------------------ 5 method
    R.h1("5  Phân tích chuyên sâu MP-SENet")
    R.h2("5.1  Tổng quan kiến trúc")
    R.p(f"Hình {R.fig_no + 1} cho thấy toàn bộ mô hình. Bản cài đặt lại của chúng tôi có **2,047,000 tham số**, khớp với "
        "con số 2.05 M trong bài báo.")
    R.figure("fig_architecture.png", "MP-SENet. Một encoder dùng chung và bốn khối two-stage Conformer cấp dữ liệu cho "
             "hai decoder song song: một cho biên độ, một cho pha. iSTFT kết hợp chúng thành dạng sóng đã tăng cường.")
    R.bullets([
        "**Đầu vào.** STFT nhiễu được tách thành *biên độ nén* |Y|^0.3 và pha ∠Y, xếp thành hai kênh "
        "(201 bin tần số × T khung).",
        "**Dense encoder.** Các lớp tích chập với kết nối dense và độ giãn (dilation) tăng dần theo thời gian nhìn được "
        "ngữ cảnh rộng với chi phí thấp. Một lớp tích chập có bước (stride) chia đôi trục tần số (201 → 100) để tiết kiệm "
        "tính toán.",
        f"**Bốn khối TS-Conformer** (Hình {R.fig_no + 1}) mô hình hóa phụ thuộc xa theo thời gian và theo tần số.",
        "**Decoder biên độ.** Upsample trở lại 201 bin và xuất ra một *mask*. Biên độ tăng cường là mask × |Y|.",
        "**Decoder pha.** Xuất hai giá trị (r, i) cho mỗi bin; pha là atan2(i, r). Cách này tránh được vấn đề pha bị "
        "quấn tại ±π."])
    R.figure("fig_tfblock.png", "Một khối two-stage (TS) Conformer. Cùng một feature map được xử lý như các chuỗi theo "
             "thời gian, rồi như các chuỗi theo tần số.", width_cm=15)
    R.h2("5.2  Ba lựa chọn thiết kế nhỏ nhưng ảnh hưởng lớn")
    R.figure("fig_compression_mask.png", "Trái: nén lũy thừa (c = 0.3) cho các bin nhỏ nhưng quan trọng nhiều trọng số "
             "hơn. Phải: sigmoid học được với β = 2 cho phép mask vượt quá 1, nên có thể khôi phục tiếng nói bị suy giảm.")
    R.bullets(["**Nén biên độ (c = 0.3).** Phổ tiếng nói trải trên một dải âm lượng rất rộng. Nâng lên lũy thừa 0.3 làm "
               "các bin nhỏ nổi lên, để mạng và loss không bỏ qua chúng. Việc bỏ nén (a08) được để lại cho hướng phát "
               "triển.",
               "**Mask sigmoid học được (β = 2).** Sigmoid thông thường chỉ giảm được năng lượng. Với β = 2 và độ dốc "
               "học được cho từng tần số, mask còn có thể khuếch đại (sigmoid thường, a10, là hướng phát triển).",
               "**Pha qua atan2.** Dự đoán (r, i) rồi lấy góc luôn cho một pha hợp lệ. Ablation a03 thay thế phần này "
               "bằng pha nhiễu."])
    R.h2("5.3  Các hàm mục tiêu huấn luyện")
    R.p(f"Mô hình được huấn luyện đồng thời với sáu loss (Hình {R.fig_no + 1}).")
    R.figure("fig_losses.png", "Sáu hàm mục tiêu và trọng số của chúng trong loss tổng.", width_cm=13.5)
    R.bullets(["**Magnitude MSE:** khoảng cách giữa biên độ nén của tín hiệu sạch và tín hiệu tăng cường.",
               "**Loss pha:** so sánh pha tức thời (instantaneous phase, IP), sai phân của nó theo tần số (group delay, "
               "GD) và theo thời gian (instantaneous angular frequency, IAF), tất cả qua một hàm *anti-wrapping* "
               f"(Hình {R.fig_no + 1}).",
               "**Complex MSE:** khoảng cách giữa phần thực và phần ảo đã nén.",
               "**Time L1:** khoảng cách giữa hai dạng sóng.",
               "**STFT consistency:** phân tích lại dạng sóng đầu ra phải cho lại đúng spectrogram đã dự đoán.",
               "**Metric GAN:** một discriminator học dự đoán PESQ chuẩn hóa; generator được thưởng khi discriminator "
               "cho rằng đầu ra của nó là hoàn hảo."])
    R.figure("fig_phase_wrapping.png", "Vì sao pha cần một loss đặc biệt. Pha chỉ xác định sai khác bội số của 2π "
             "(phải). Một loss ngây thơ phạt rất nặng sai số 2π, dù đó hoàn toàn không phải sai số (trái, màu xám); hàm "
             "anti-wrapping coi nó bằng không (trái, màu đỏ).")
    R.h2("5.4  Thiết lập huấn luyện")
    R.table([["Thiết lập", "Giá trị"],
             ["Tần số lấy mẫu / STFT", "16 kHz; FFT 400, hop 100, cửa sổ Hann 400 (25 ms / 6.25 ms)"],
             ["Đoạn huấn luyện", "cắt ngẫu nhiên 2 s, batch size 4"],
             ["Optimizer", "AdamW, learning rate 5·10⁻⁴, β = (0.8, 0.99); learning rate × 0.99 sau mỗi epoch"],
             ["Thời lượng huấn luyện", "5 epoch cho mọi lần chạy (giới hạn tài nguyên); xem Mục 6.2"],
             ["Kích thước mô hình", "64 kênh, 4 khối TS-Conformer, 4 attention head, kernel tích chập 31"],
             ["Chọn mô hình", "PESQ tốt nhất trên tập người nói validation được tách riêng"],
             ["Chuẩn hóa đầu vào", "mỗi câu nhiễu được chuẩn hóa về RMS đơn vị; đầu ra được scale ngược lại"]],
            [4.6, 11.8], caption="Cấu hình huấn luyện (`configs/base.yaml`).", center_from=9)

    # ------------------------------------------------------------ 6 ablation
    R.h1("6  Nghiên cứu ablation")
    R.h2("6.1  Ý tưởng")
    R.p("**Nghiên cứu ablation** bỏ hoặc thay một thành phần mỗi lần và đo xem mô hình kém đi (hoặc tốt lên) bao nhiêu. "
        "Mức giảm càng lớn thì thành phần đó càng quan trọng. Mọi thí nghiệm dùng cùng dữ liệu, seed, số epoch và quy tắc "
        "chọn mô hình; chỉ một thiết lập thay đổi.")
    R.p("Do giới hạn GPU, chúng tôi chọn **bốn ablation kiểm tra các ý tưởng chính của MP-SENet**: metric GAN (tín hiệu "
        "huấn luyện), các loss pha và decoder pha (luận điểm cốt lõi của bài báo), và backbone Conformer (kiến trúc). Sáu "
        "ablation còn lại đã được cài đặt và liệt kê ở Mục 6.6 như hướng phát triển.")
    R.h2("6.2  Quy trình")
    R.p("Mỗi lần chạy huấn luyện **5 epoch**, ngắn hơn nhiều so với bài báo, nên điểm tuyệt đối thấp hơn PESQ 3.50 đã "
        "công bố. Vì mọi lần chạy có cùng ngân sách, seed và quy tắc chọn mô hình, *chênh lệch* giữa các lần chạy vẫn là "
        "một phép so sánh công bằng; các chênh lệch nhỏ cần được đọc thận trọng (Mục 6.5).")
    R.figure("fig_split.png", "Chia dữ liệu. Hai người nói trong tập huấn luyện được tách ra làm validation, nên tập "
             "test chỉ được dùng một lần, cho kết quả cuối cùng. (Mã gốc chọn mô hình trên tập test, làm kết quả bị "
             "thổi phồng nhẹ.)", width_cm=14)
    R.figure("fig_pipeline.png", "Quy trình thí nghiệm. Mỗi cấu hình kế thừa `base.yaml` và đổi một khóa; 7 lần chạy "
             "được gửi thành một SLURM job array; kết quả được tổng hợp thành bảng và hình.", width_cm=15.5)
    R.h2("6.3  Các thí nghiệm")
    R.table([["ID", "Thay đổi", "Câu hỏi cần trả lời"]] + [list(a) for a in ABLATIONS],
            [1.2, 6.6, 8.6], caption="Bốn ablation đã chạy. a00 là baseline đầy đủ.", size=10, center_from=9)
    R.h2("6.4  Kết quả")
    if rows:
        base = next((r for r in rows if r["run"] == "a00_baseline"), None)
        trows = [["Lần chạy", "Mô tả", "PESQ", "ΔPESQ", "CSIG", "CBAK", "COVL", "STOI", "SI-SDR"]]
        hl = []
        for r in rows:
            if r["run"].startswith("p"):
                continue
            dp = f"{float(r['pesq']) - float(base['pesq']):+.3f}" if base and r["run"] != "noisy" else "–"
            trows.append([r["run"].split("_")[0], vi_desc(r), fnum(r["pesq"], 3), dp, fnum(r["csig"]),
                          fnum(r["cbak"]), fnum(r["covl"]), fnum(r["stoi"], 3), fnum(r["si_sdr"])])
            if r["run"] == "a00_baseline":
                hl.append(len(trows) - 1)
        R.table(trows, [1.4, 4.8, 1.5, 1.5, 1.4, 1.4, 1.4, 1.5, 1.5], highlight=tuple(hl), size=9,
                caption="Kết quả ablation trên 824 câu test. ΔPESQ so với baseline đầy đủ (a00).")
        R.figure("fig_results.png", "PESQ của từng lần chạy. Đường nét đứt là baseline đầy đủ; cột xanh lá là các cải "
                 "tiến đề xuất.")
        if base:
            ab = sorted([r for r in rows if r["run"].startswith("a") and r is not base], key=lambda r: float(r["pesq"]))
            R.p("**Các thành phần mà khi bỏ đi gây thiệt hại nhiều nhất:**")
            R.bullets([f"**{r['run'].split('_')[0]}** ({vi_desc(r)}): "
                       f"{float(r['pesq']) - float(base['pesq']):+.3f} PESQ" for r in ab[:3]])
    else:
        R.table([["Lần chạy", "Mô tả", "PESQ", "ΔPESQ", "CSIG", "CBAK", "COVL", "STOI", "SI-SDR"],
                 ["noisy", VI_DESC["noisy"], *["TBD"] * 7], ["a00", VI_DESC["a00"], *["TBD"] * 7]] +
                [[a[0], a[1], *["TBD"] * 7] for a in ABLATIONS],
                [1.4, 4.8, 1.5, 1.5, 1.4, 1.4, 1.4, 1.5, 1.5], highlight=(2,), size=9,
                caption="Kết quả ablation trên 824 câu test (sẽ được điền tự động).")
        R.callout("Đang chờ kết quả", "Các lần huấn luyện đang chạy trên cụm HPC. Sau khi chạy "
                  "`scripts/collect_results.py`, build lại báo cáo này sẽ điền bảng, thêm hình kết quả và liệt kê các "
                  "thành phần quan trọng nhất.")
    R.h2("6.5  Kỳ vọng và cách đọc các con số")
    R.bullets(["**a03 (pha nhiễu)** được kỳ vọng gây một trong những mức giảm lớn nhất, vì pha tường minh là đóng góp "
               "chính của bài báo. Khác biệt thường *nghe* thấy rõ hơn (tiếng rè, giống robot) là thấy trong PESQ.",
               "**a01 (không GAN)** được kỳ vọng làm giảm PESQ nhưng có thể *tăng* SI-SDR: discriminator tối ưu chất "
               "lượng cảm nhận chứ không phải độ chính xác dạng sóng. So sánh cả hai metric cho biết GAN có chỉ đang "
               "khớp theo PESQ hay không.",
               "**a02 (không loss pha)** cho biết decoder pha có cần giám sát trực tiếp không; kết hợp với a03, nó tách "
               "được giá trị của các *loss* pha với giá trị của *decoder* pha.",
               "**a04 (BiLSTM)** cho biết bao nhiêu phần chất lượng đến từ attention.",
               "Chênh lệch khoảng **±0.03 PESQ** nằm trong dao động giữa các lần chạy trên benchmark này. Với các trường "
               "hợp sát nhau, nên chạy lại với 2–3 seed và làm kiểm định cặp (paired test) trên điểm từng câu "
               "(`per_file.csv`). Sau chỉ 5 epoch mô hình vẫn đang cải thiện, nên chúng tôi coi các chênh lệch dưới "
               "khoảng 0.05 PESQ là chưa kết luận được."])
    R.h2("6.6  Hướng phát triển")
    R.p("Các thí nghiệm sau đã được cài đặt đầy đủ (mỗi thí nghiệm một file cấu hình trong `configs/ablation/`) và có "
        "thể chạy bằng cùng script (`EXPERIMENTS=configs/experiments_full.txt`), nhưng chưa vừa với ngân sách tính toán "
        "của chúng tôi:")
    R.table([["ID", "Thay đổi", "Câu hỏi cần trả lời"]] + [list(a) for a in FUTURE_ABLATIONS],
            [1.2, 6.6, 8.6], caption="Đã cài đặt nhưng chưa chạy: hướng phát triển.", size=10, center_from=9)

    # ------------------------------------------------------------ 7 improvements
    R.h1("7  Đề xuất cải tiến")
    R.p("Cả hai đề xuất chỉ thay đổi khâu **huấn luyện**, nên mô hình sau huấn luyện chạy nhanh đúng bằng baseline.")
    R.h2("7.1  P1: loss STFT đa phân giải (multi-resolution STFT)")
    R.p("Mọi loss phổ của MP-SENet đều dùng một độ phân giải STFT duy nhất (cửa sổ 25 ms). Cửa sổ ngắn cho chi tiết thời "
        "gian tốt nhưng chi tiết tần số kém, cửa sổ dài thì ngược lại. **Loss multi-resolution STFT** so sánh dạng sóng "
        "tăng cường và dạng sóng sạch ở ba độ phân giải (FFT 256, 512 và 1024 điểm), dùng spectral convergence cộng "
        "khoảng cách log-magnitude. Loss này được kỳ vọng phạt các lỗi như pre-echo và onset bị nhòe mà một độ phân "
        "giải bỏ sót. Trọng số: 0.1 (`loss.mrstft=0.1`).")
    R.h2("7.2  P2: perceptual contrast stretching (PCS)")
    R.p("PCS làm *mục tiêu huấn luyện* sắc nét hơn một chút so với tiếng nói sạch thật. Log-magnitude của phổ sạch được "
        "nhân với một hệ số khuếch đại phụ thuộc tần số trong khoảng 1.0 đến 1.4. Hệ số mạnh nhất áp dụng quanh "
        f"0.4–4.4 kHz, các dải quan trọng nhất cho độ dễ hiểu (Hình {R.fig_no + 1}). SEMamba báo cáo mức tăng khoảng 0.14 "
        "PESQ nhờ PCS trên backbone Mamba; chúng tôi kiểm tra xem hiệu quả này có chuyển sang MP-SENet dựa trên "
        "Conformer không (`data.pcs=true`).")
    R.figure("fig_pcs.png", "Hệ số khuếch đại PCS theo tần số (FFT 400 điểm ở 16 kHz).", width_cm=14)
    R.h2("7.3  Kết quả")
    prow = [["Lần chạy", "Thay đổi", "PESQ", "ΔPESQ so với a00", "STOI", "SI-SDR"],
            ["p01", "+ loss multi-resolution STFT", "TBD", "TBD", "TBD", "TBD"],
            ["p02", "+ mục tiêu PCS", "TBD", "TBD", "TBD", "TBD"]]
    if rows:
        rmap = {r["run"].split("_")[0]: r for r in rows}
        b = rmap.get("a00")
        for row in prow[1:]:
            r = rmap.get(row[0])
            if r:
                row[2:] = [fnum(r["pesq"], 3), f"{float(r['pesq']) - float(b['pesq']):+.3f}" if b else "–",
                           fnum(r["stoi"], 3), fnum(r["si_sdr"])]
    R.table(prow, [1.6, 5.6, 2.0, 3.0, 2.0, 2.2], caption="Các cải tiến đề xuất trên tập test.")
    R.h2("7.4  Các ý tưởng khác (chưa cài đặt)")
    R.bullets(["**Kết hợp P1 và P2** (cấu hình `p03`): chỉ đáng làm nếu mỗi đề xuất có ích khi đứng riêng.",
               "**Huấn luyện lâu hơn** cho baseline và đề xuất tốt nhất, để so sánh với các con số đã công bố.",
               "**Khối Mamba** thay cho Conformer: chi phí tuyến tính theo độ dài câu (SEMamba).",
               "**Phiên bản causal / streaming** với chunked attention, để dùng thời gian thực trong cuộc gọi và máy trợ "
               "thính.",
               "**Dữ liệu tiếng Việt:** xây dựng một tập nhiễu/sạch tiếng Việt (ví dụ VIVOS trộn với nhiễu DEMAND/MUSAN) "
               "và fine-tune.",
               "**Tổng quát hóa:** huấn luyện hoặc test trên dữ liệu DNS-Challenge lớn hơn."])

    # ------------------------------------------------------------ 8 repo
    R.h1("8  Cài đặt và khả năng tái lập")
    R.p("Mã nguồn được tổ chức như một repository nghiên cứu Python tiêu chuẩn: file cấu hình, một package trong `src/`, "
        "các script, file job SLURM và unit test.")
    R.table([["Thư mục", "Nội dung"],
             ["configs/", "`base.yaml` (baseline), `ablation/a01…a10, p01…p03` (mỗi file một thay đổi), `debug.yaml`"],
             ["src/se/", "nạp dữ liệu, mô hình, loss, metric, `train.py`, `evaluate.py`, `enhance.py`"],
             ["scripts/", "tải dữ liệu, tổng hợp kết quả, demo mô hình chính thức, chấm điểm một thư mục bất kỳ"],
             ["slurm/", "chạy đơn lẻ, job array cho mọi thí nghiệm, multi-GPU, baseline đầu vào nhiễu"],
             ["notebooks/", "notebook demo: nghe và so sánh các lần chạy ablation"],
             ["tests/", "unit test cho kích thước tensor, loss, metric và cấu hình"],
             ["docs/", "tổng quan tài liệu, thiết kế ablation, slide và báo cáo này (cả hai được sinh tự động)"]],
            [3.4, 13.0], caption="Cấu trúc repository.", center_from=9)
    R.p("Tái lập toàn bộ chỉ cần năm lệnh:")
    cmds = [("pip install -e \".[dev]\" && pytest -q", "cài đặt và chạy test"),
            ("python scripts/prepare_vbd.py --out data", "tải + resample VoiceBank-DEMAND"),
            ("sbatch --array=0-6%1 slurm/ablation_array.sbatch", "huấn luyện + đánh giá 7 lần chạy"),
            ("python scripts/collect_results.py", "bảng và biểu đồ kết quả"),
            ("python docs/report/build_report.py", "build lại báo cáo này")]
    R.code([f"{c:<52}# {d}" for c, d in cmds])
    R.p("Các kiểm tra đã thực hiện: cả 21 unit test đều qua; một lần chạy thử end-to-end trên dữ liệu tổng hợp hoàn tất "
        "huấn luyện, bước discriminator, lưu checkpoint và đánh giá trên tập test; mô hình đầy đủ có 2.047 M tham số, "
        "khớp với bài báo. Job huấn luyện tự động tiếp tục từ checkpoint cuối nếu chạm giới hạn thời gian của cụm. PESQ "
        "cho discriminator được tính song song trên nhiều tiến trình CPU để tăng tốc huấn luyện.")

    # ------------------------------------------------------------ 9 conclusion
    R.h1("9  Kết luận")
    R.p("Tăng cường tiếng nói đã đi từ các mask biên độ đơn giản đến các mô hình ước lượng pha tường minh, học từ metric "
        "cảm nhận, và gần đây là sinh tiếng nói bằng diffusion hoặc language model. Các mô hình discriminative như "
        "MP-SENet vẫn cho điểm tốt nhất trên benchmark chuẩn so với kích thước, trong khi mô hình sinh bền vững hơn trong "
        "điều kiện chưa gặp.")
    R.p("Chúng tôi đã cài đặt lại MP-SENet, xây dựng một framework ablation tái lập được hoàn toàn, chạy bốn ablation "
        "một yếu tố cho các ý tưởng chính (sáu ablation khác đã sẵn sàng để chạy), và đề xuất hai cải tiến chỉ ở khâu "
        "huấn luyện. Nghiên cứu cho thấy *những* thành phần nào trong số rất nhiều thành phần của MP-SENet thực sự tạo "
        "nên hiệu năng của nó, từ đó gợi ý thực tế cho việc xây dựng mô hình nhỏ hơn hoặc nhanh hơn và áp dụng cho ngôn "
        "ngữ mới như tiếng Việt.")

    # ------------------------------------------------------------ appendix + refs
    R.h1("Phụ lục A  Phân công công việc")
    R.table([["Thành viên", "MSHV", "Công việc", "Tỉ lệ"],
             ["Chau Kien Dat", "25C15036", "Khảo sát tài liệu (P1–P6) và so sánh, demo mô hình chính thức và notebook, "
              "slide; viết toàn bộ báo cáo", "50%"],
             ["Nguyen Vi Khang", "25C15043", "Cài đặt lại mô hình, cấu hình, huấn luyện trên HPC, metric đánh giá, phân tích "
              "ablation, cải tiến đề xuất; quay video thuyết trình", "50%"]],
            [3.2, 2.6, 8.8, 1.8], center_from=3)

    R.h1("Tài liệu tham khảo")
    refs = [
        "S. Abdulatif, R. Cao, B. Yang. CMGAN: Conformer-based metric-GAN for monaural speech enhancement. IEEE/ACM TASLP, 32, 2024.",
        "Y.-X. Lu, Y. Ai, Z.-H. Ling. MP-SENet: A speech enhancement model with parallel denoising of magnitude and phase spectra. Interspeech 2023.",
        "J. Richter, S. Welker, J.-M. Lemercier, B. Lay, T. Gerkmann. Speech enhancement and dereverberation with diffusion-based generative models. IEEE/ACM TASLP, 31, 2023.",
        "J.-M. Lemercier, J. Richter, S. Welker, T. Gerkmann. StoRM: A diffusion-based stochastic regeneration model for speech enhancement and dereverberation. IEEE/ACM TASLP, 31, 2023.",
        "W. Tai, Y. Lei, F. Zhou, G. Trajcevski, T. Zhong. DOSE: Diffusion dropout with adaptive prior for speech enhancement. NeurIPS 2023.",
        "J. Yao, H. Liu, C. Chen, Y. Hu, E. S. Chng, L. Xie. GenSE: Generative speech enhancement via language models using hierarchical modeling. ICLR 2025.",
        "S.-W. Fu et al. MetricGAN+: An improved version of MetricGAN for speech enhancement. Interspeech 2021.",
        "H. Schröter, A. N. Escalante-B., T. Rosenkranz, A. Maier. DeepFilterNet: A low complexity speech enhancement framework for full-band audio based on deep filtering. ICASSP 2022.",
        "R. Chao et al. An investigation of incorporating Mamba for speech enhancement. IEEE SLT 2024.",
        "R. Yamamoto, E. Song, J.-M. Kim. Parallel WaveGAN: A fast waveform generation model based on generative adversarial networks with multi-resolution spectrogram. ICASSP 2020.",
        "C. Valentini-Botinhao, X. Wang, S. Takaki, J. Yamagishi. Investigating RNN-based speech enhancement methods for noise-robust text-to-speech. SSW 2016.",
        "Y. Hu, P. C. Loizou. Evaluation of objective quality measures for speech enhancement. IEEE TASLP, 16(1), 2008.",
    ]
    for i, ref in enumerate(refs, 1):
        q = R.doc.add_paragraph()
        q.paragraph_format.left_indent = Cm(0.8)
        q.paragraph_format.first_line_indent = Cm(-0.8)
        q.paragraph_format.space_after = Pt(4)
        r = q.add_run(f"[{i}]  {ref}")
        r.font.size = Pt(10)

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    R.save(out_docx)
    print(f"[report] {R.fig_no} figures, {R.tab_no} captioned tables -> {out_docx} "
          f"(results: {'filled' if rows else 'pending'})")



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "ablation_results.csv"))
    ap.add_argument("--data", default=str(ROOT / "data" / "voicebank_demand_16k"))
    ap.add_argument("--out", default=str(HERE / "report.docx"))
    a = ap.parse_args()
    build(Path(a.out), Path(a.results), Path(a.data))


if __name__ == "__main__":
    main()
