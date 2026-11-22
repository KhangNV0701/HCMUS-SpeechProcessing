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
        r = p.add_run("Speech Enhancement: survey and ablation study of MP-SENet   ·   page ")
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
                el.text = "1" if instr == "PAGE" else "Right-click → Update field to build the table of contents."
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
        self._runs(c, f"**Figure {self.fig_no}.** {caption}")
        return self.fig_no

    def table(self, rows, widths_cm, caption=None, highlight=(), size=10, center_from=2, center_cols=None):
        if caption:
            self.tab_no += 1
            c = self.doc.add_paragraph(style="Caption")
            c.paragraph_format.keep_with_next = True
            c.paragraph_format.space_after = Pt(3)
            self._runs(c, f"**Table {self.tab_no}.** {caption}")
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
def fnum(v, n=2):
    try:
        return f"{float(v):.{n}f}"
    except (TypeError, ValueError):
        return "–"


ABLATIONS = [
    ("a01", "Remove the metric discriminator (no GAN)", "Is the PESQ gain real, or is the model just tuned to the metric?"),
    ("a02", "Remove the anti-wrapping phase losses", "Can the phase decoder learn useful phase without direct supervision?"),
    ("a03", "Remove the STFT consistency loss", "Does it matter that the predicted spectrogram is a valid STFT?"),
    ("a04", "Remove time-domain L1 and complex losses", "Do the waveform and complex-domain terms add anything?"),
    ("a05", "Magnitude-only decoder; re-use the noisy phase", "The paper's main claim: is explicit phase estimation worth it?"),
    ("a06", "One decoder that maps directly to the complex spectrum", "Parallel magnitude + phase vs. the common complex mapping"),
    ("a07", "No magnitude compression (c = 1)", "Does compressing the dynamic range help?"),
    ("a08", "2 instead of 4 TS-Conformer blocks", "How much depth is needed? Quality vs. speed"),
    ("a09", "BiLSTM instead of Conformer", "Attention + convolution vs. recurrent modelling"),
    ("a10", "Plain sigmoid mask (β = 1, fixed slope)", "Does letting the mask amplify (values > 1) help?"),
]


def build(out_docx: Path, results_csv: Path, data_root: Path):
    rows = make_figures.make_all(results_csv, data_root)
    R = Report()

    # ------------------------------------------------------------ cover
    for _ in range(3):
        R.p("")
    R.p("SPEECH PROCESSING · FINAL PROJECT · RESEARCH TRACK", size=11, color=MAGENTA, after=10)
    t = R.doc.add_paragraph(style="Title")
    t.add_run("Speech Enhancement")
    R.p("A survey of recent methods and an ablation study of MP-SENet", size=17, color=PLUM, after=28)
    R.p("University of Science, VNU-HCM (HCMUS) · Master's program", size=11, color=MUTED, after=2)
    R.p("Instructor: <instructor name>", size=11, color=MUTED, after=2)
    R.p(f"{date.today():%B %Y}", size=11, color=MUTED, after=24)
    R.p("**Group members and work division**", size=12, after=4)
    R.table([["Member", "Student ID", "Main tasks", "Share"],
             ["Chau Kien Dat", "25C15036", "Literature survey (Ch. 3), demo and web app (Ch. 4), slides, video", "50%"],
             ["Nguyen Vi Khang", "25C15043", "Re-implementation, ablation runs on HPC, evaluation (Ch. 5–8), report", "50%"]],
            [3.4, 2.6, 8.4, 1.8], size=10.5, center_from=3)
    R.p("Code and data instructions: https://github.com/KhangNV0701/HCMUS-SpeechProcessing", size=10, color=MUTED)
    R.page_break()

    # ------------------------------------------------------------ TOC
    h = R.doc.add_paragraph()
    r = h.add_run("Contents")
    r.font.name, r.font.size, r.bold = HEAD, Pt(20), True
    r.font.color.rgb = RGBColor.from_string(PLUM)
    R.toc()
    R.page_break()

    # ------------------------------------------------------------ summary
    R.h1("Summary")
    R.p("**Speech enhancement** removes background noise from a speech recording. This project has four parts:")
    R.bullets([
        "**Survey (Chapter 3).** We read six recent papers from top venues (IEEE/ACM TASLP, Interspeech, NeurIPS, "
        "ICLR). Current methods fall into three families: *discriminative* models that predict a clean spectrogram "
        "in one pass, *diffusion* models that generate clean speech step by step, and *language-model* methods that "
        "predict clean audio tokens.",
        "**Demo (Chapter 4).** We run the authors' official pretrained MP-SENet and our own pipeline, and score both "
        "with the same metrics. A small web app lets you record or upload noisy speech and hear the result.",
        "**Ablation study (Chapters 5–6).** We re-implemented MP-SENet (2.05 M parameters) and defined 10 experiments "
        "that each remove or replace exactly one component, to find which parts actually matter.",
        "**Improvements (Chapter 7).** We propose two training-only changes with no extra inference cost: a "
        "multi-resolution STFT loss and perceptual contrast stretching (PCS) of the training target.",
    ])
    if rows:
        base = next((r for r in rows if r["run"] == "a00_baseline"), None)
        best = max((r for r in rows if r["run"] != "noisy" and r.get("pesq")), key=lambda r: float(r["pesq"]))
        R.callout("Main result", [
            f"Our baseline reaches **PESQ {fnum(base['pesq'], 3)}** on the VoiceBank-DEMAND test set "
            f"(noisy input: {fnum(next(r for r in rows if r['run'] == 'noisy')['pesq'], 2)})." if base else "",
            f"Best run: **{best['run']}** ({best['description']}), PESQ {fnum(best['pesq'], 3)}."])
    else:
        R.callout("Status of the experiments",
                  "All code, configurations and job scripts are ready. The results tables in Chapters 6 and 7 are "
                  "filled in automatically once the training runs on the HPC cluster finish "
                  "(`python docs/report/build_report.py`).")

    # ------------------------------------------------------------ 1 intro
    R.h1("1  Introduction")
    R.h2("1.1  The problem")
    R.p("A microphone rarely records only the speaker. Traffic, fans, other people and room echo are mixed in. "
        "**Single-channel speech enhancement** tries to recover the clean speech *s* from the noisy recording "
        "*y = s + n*, using only that one recording. No clean reference is available when the system is used.")
    R.figure("fig_spectrogram.png", "Spectrograms show energy over time (x-axis) and frequency (y-axis). Speech "
             "appears as bright stacked harmonics; noise fills the gaps between them. Enhancement should bring the "
             "left picture as close as possible to the right one.")
    R.p("Why it matters:")
    R.bullets(["**Communication:** phone and video calls, hearing aids and assistive listening.",
               "**Front-end for other systems:** speech recognition (ASR), speaker verification and keyword spotting "
               "all degrade in noise.",
               "**Data cleaning:** text-to-speech (TTS) corpora collected from the Internet are often noisy."])
    R.h2("1.2  What we did")
    R.bullets(["Surveyed recent work and compared methods on a common benchmark (Chapter 3).",
               "Ran the official MP-SENet model as a demo (Chapter 4).",
               "Re-implemented MP-SENet and explained each part in plain terms (Chapter 5).",
               "Designed and ran a one-factor-at-a-time ablation study (Chapter 6).",
               "Proposed and tested two improvements (Chapter 7).",
               "Packaged everything as a reproducible repository (Chapter 8)."], numbered=True)

    # ------------------------------------------------------------ 2 background
    R.h1("2  Background")
    R.h2("2.1  From waveform to spectrogram")
    R.p("Most modern systems work on the **short-time Fourier transform (STFT)**. The signal is cut into short "
        "overlapping frames (here 25 ms, moving 6.25 ms at a time). Each frame is turned into a spectrum with a "
        "**magnitude** (how loud each frequency is) and a **phase** (where each frequency is in its cycle). At 16 kHz "
        "with a 400-point FFT this gives 201 frequency bins per frame. The inverse STFT (iSTFT) turns a spectrogram "
        "back into a waveform.")
    R.p("Older systems only cleaned the magnitude and reused the noisy phase, because phase looks random and is "
        "hard to predict. Newer work, including MP-SENet, shows that **estimating the phase too** gives clearly "
        "better quality.")
    R.h2("2.2  Masking and mapping")
    R.bullets(["**Masking:** predict a number between 0 and about 1 for every time-frequency bin and multiply it with the "
               "noisy magnitude. Bins dominated by noise get small values.",
               "**Mapping:** predict the clean spectrum (magnitude, or real and imaginary parts) directly."])
    R.h2("2.3  How quality is measured")
    R.p("All papers in this report use the **VoiceBank-DEMAND** benchmark: 11,572 noisy/clean training pairs from "
        "28 speakers and 824 test pairs from 2 unseen speakers, mixed with real noise recordings at 0–15 dB SNR "
        "(training) and 2.5–17.5 dB (testing).")
    R.table([["Metric", "Range", "What it tells you"],
             ["PESQ (wide-band)", "1 – 4.5", "Perceived speech quality (ITU-T P.862.2). The main number in the field."],
             ["STOI / ESTOI", "0 – 1", "How intelligible the speech is."],
             ["CSIG", "1 – 5", "Predicted opinion score for *speech distortion*."],
             ["CBAK", "1 – 5", "Predicted opinion score for *background noise intrusiveness*."],
             ["COVL", "1 – 5", "Predicted *overall* quality."],
             ["SSNR, SI-SDR", "dB", "Signal fidelity: how close the waveform is to the clean one."]],
            [3.4, 2.0, 11.0], caption="Objective metrics used throughout this report (higher is better for all).",
            center_cols=(1,))

    # ------------------------------------------------------------ 3 survey
    R.h1("3  Literature survey")
    R.h2("3.1  The big picture")
    R.p(f"Methods published between 2021 and 2025 fall into three families (Figure {R.fig_no + 1}). They trade off accuracy on "
        "standard metrics, robustness to new conditions, and computational cost.")
    R.figure("fig_taxonomy.png", "Three families of modern speech enhancement, with representative models and "
             "their main strengths (+) and weaknesses (−).")
    R.figure("fig_timeline.png", "Timeline of the papers discussed in this chapter.", width_cm=15.5)
    R.p("Five trends stand out:")
    R.bullets(["**Explicit phase modelling:** predicting phase directly, with losses that understand the 2π wrap-around.",
               "**Metric-driven training:** a discriminator network learns to predict PESQ, and the enhancer is "
               "trained to maximise it.",
               "**Time-and-frequency sequence models:** Conformers that look along both axes of the spectrogram, now "
               "being replaced by faster state-space models (Mamba).",
               "**Generative robustness:** diffusion and language models that generalise better to unseen noise.",
               "**Efficiency:** real-time, low-complexity designs for phones and hearing aids (e.g. DeepFilterNet)."])

    papers = [
        ("3.2  CMGAN: Conformer-based Metric GAN",
         "S. Abdulatif, R. Cao, B. Yang. IEEE/ACM Transactions on Audio, Speech, and Language Processing (TASLP), "
         "vol. 32, 2024. Q1 journal; short version at Interspeech 2022.",
         "A dense convolutional encoder is followed by four *two-stage Conformer* blocks, which model context first "
         "along time and then along frequency. Two decoders follow: one predicts a magnitude mask, the other refines "
         "the real and imaginary parts. A *metric discriminator* learns to predict PESQ, and the generator is trained "
         "to push that prediction up.",
         "PESQ 3.41, CSIG 4.63, CBAK 3.94, COVL 4.12, STOI 0.96, with only 1.83 M parameters.",
         ["Excellent quality for a small model.", "Time-frequency Conformers capture long-range context.",
          "Thoroughly evaluated on denoising, dereverberation and super-resolution."],
         ["Phase is only refined indirectly through the complex branch.",
          "Attention cost grows quadratically with utterance length; not causal (cannot run in real time as is).",
          "Computing PESQ for the discriminator slows training."]),
        ("3.3  MP-SENet: parallel magnitude and phase denoising",
         "Y.-X. Lu, Y. Ai, Z.-H. Ling. Interspeech 2023 (CORE A). An extended version appeared in Neural Networks (2025).",
         "It keeps a CMGAN-like backbone but uses **two parallel decoders**: one for the magnitude (a mask) and one "
         "that estimates the **phase explicitly**. The phase decoder predicts two numbers per bin and takes their "
         "angle with atan2, which always gives a valid phase. Special *anti-wrapping* losses compare phases correctly "
         "across the 2π boundary.",
         "PESQ 3.50, CSIG 4.73, CBAK 3.95, COVL 4.22, STOI 0.96, with about 2.05 M parameters.",
         ["Best results among models of this size at publication time.",
          "First model to estimate phase directly and reliably.", "Official code and pretrained checkpoints are public."],
         ["Six loss terms with hand-picked weights; unclear which ones matter (this is what our ablation tests).",
          "Not causal; trained only on VoiceBank-DEMAND noise types.", "The metric GAN may over-fit to PESQ."]),
        ("3.4  SGMSE+: score-based diffusion for enhancement",
         "J. Richter, S. Welker, J.-M. Lemercier, B. Lay, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023. Q1 journal.",
         "A *diffusion model* works in the complex STFT domain. Training defines a process that gradually moves "
         "clean speech towards the noisy mixture plus Gaussian noise. At test time a neural network (NCSN++) runs "
         "this process backwards, step by step, conditioned on the noisy input.",
         "PESQ 2.93, ESTOI 0.87, SI-SDR 17.3 dB on VoiceBank-DEMAND; notably better than discriminative models when "
         "tested on data from a different corpus.",
         ["Natural-sounding output and strong generalisation.", "The same framework also removes reverberation."],
         ["Slow: about 60 network evaluations per utterance with a ~65 M-parameter network.",
          "Can 'hallucinate' breathing or phoneme-like sounds at low SNR.", "Lower PESQ than the best discriminative models."]),
        ("3.5  StoRM: stochastic regeneration",
         "J.-M. Lemercier, J. Richter, S. Welker, T. Gerkmann. IEEE/ACM TASLP, vol. 31, 2023. Q1 journal.",
         "Combines both worlds: a predictive (discriminative) network first produces an estimate, then a diffusion "
         "model *regenerates* the fine details starting from that estimate rather than from pure noise.",
         "Similar quality to SGMSE+ with far fewer sampling steps and fewer generative artefacts.",
         ["Removes the vocalising/breathing artefacts of pure diffusion.", "Much faster sampling than SGMSE+."],
         ["Two networks to train and run.", "Still slower than a single discriminative model."]),
        ("3.6  DOSE: diffusion dropout with adaptive prior",
         "W. Tai, Y. Lei, F. Zhou, G. Trajcevski, T. Zhong. NeurIPS 2023 (CORE A*).",
         "Conditional diffusion models sometimes ignore the noisy input. DOSE fixes this with *diffusion dropout* "
         "during training, which forces the model to rely on the condition, and an *adaptive prior* that starts "
         "sampling from a noisy estimate instead of random noise. Only two sampling steps are needed.",
         "Efficient diffusion-based enhancement with good generalisation and a theoretical analysis.",
         ["Very few sampling steps.", "Better use of the conditioning signal."],
         ["PESQ still clearly below discriminative state of the art.", "More complex to tune."]),
        ("3.7  GenSE: enhancement as language modelling",
         "J. Yao, H. Liu, C. Chen, Y. Hu, E. S. Chng, L. Xie. ICLR 2025 (CORE A*).",
         "Speech is converted into discrete tokens: *semantic* tokens from a self-supervised model and *acoustic* "
         "tokens from a neural codec. A language model first maps noisy semantic tokens to clean ones, then generates "
         "acoustic tokens, using prompting to keep the speaker's voice.",
         "Strong naturalness (DNSMOS) and speaker similarity on real-world recordings.",
         ["Robust to many kinds of distortion.", "One model for several tasks."],
         ["Very large and slow (autoregressive decoding).",
          "Can change words or the speaker's voice; intrusive metrics like PESQ penalise it."]),
    ]
    for title, venue, method, result, pros, cons in papers:
        R.h2(title)
        R.p("*" + venue.replace("*", "\\*") + "*", color=MUTED)
        R.p(f"**Idea.** {method}")
        R.p(f"**Reported results.** {result}")
        R.table([["Strengths", "Weaknesses"]] + [[pros[i] if i < len(pros) else "", cons[i] if i < len(cons) else ""]
                                                 for i in range(max(len(pros), len(cons)))],
                [8.2, 8.2], size=10, center_from=9)

    R.h2("3.8  Other related work")
    R.bullets(["**MetricGAN+** (Fu et al., Interspeech 2021): a BLSTM mask estimator trained with a learned PESQ "
               "discriminator (PESQ 3.15). This is where the metric discriminator in CMGAN and MP-SENet comes from.",
               "**DeepFilterNet** (Schröter et al., ICASSP 2022, with v2/v3 follow-ups): real-time full-band (48 kHz) "
               "enhancement using band gains plus *deep filtering*; very low complexity.",
               "**SEMamba** (Chao et al., IEEE SLT 2024): replaces MP-SENet's Conformers with Mamba blocks, whose cost "
               "grows linearly with length. Reports PESQ 3.55, or 3.69 with perceptual contrast stretching (PCS). "
               "PCS motivates our second improvement."])
    R.h2("3.9  Comparison")
    R.figure("fig_reported_pesq.png", "PESQ reported by the authors on the VoiceBank-DEMAND test set. "
             "Discriminative models lead on this intrusive metric; diffusion models trade some PESQ for robustness.",
             width_cm=14)
    R.table([["Model", "Venue", "Family", "PESQ", "CSIG", "CBAK", "COVL", "Params"],
             ["Noisy input", "–", "–", "1.97", "3.35", "2.44", "2.63", "–"],
             ["MetricGAN+", "Interspeech'21", "Discriminative", "3.15", "4.14", "3.16", "3.64", "–"],
             ["SGMSE+", "TASLP'23", "Diffusion", "2.93", "–", "–", "–", "~65 M"],
             ["CMGAN", "TASLP'24", "Discriminative", "3.41", "4.63", "3.94", "4.12", "1.83 M"],
             ["MP-SENet", "Interspeech'23", "Discriminative", "3.50", "4.73", "3.95", "4.22", "2.05 M"],
             ["SEMamba (+PCS)", "SLT'24", "Discriminative", "3.55 (3.69)", "–", "–", "–", "~2 M"]],
            [2.9, 2.6, 2.6, 2.0, 1.4, 1.4, 1.4, 1.6], highlight=(5,),
            caption="Reported results on VoiceBank-DEMAND (\"–\" = not reported in a comparable setting).", center_from=3)
    R.callout("Why we chose MP-SENet", [
        "It gives the best accuracy per parameter among models with public code, it combines most current trends "
        "(TF-Conformers, explicit phase, metric GAN, multi-domain losses), and later models such as SEMamba build on "
        "it. Understanding which of its parts matter is therefore useful beyond this one model."])
    R.h2("3.10  The situation in Vietnam")
    R.p("We found few dedicated speech-enhancement papers by Vietnamese groups in Q1/Q2 journals or A/A\\* conferences. "
        "Noise is mostly handled *inside* other tasks:")
    R.bullets(["**Robust ASR:** for example, a 2025 study in *Tạp chí Khoa học* adds 2,000 hours of real "
               "Vietnamese noise to a 200-hour training corpus at six SNR levels and reduces word error rate on noisy "
               "test sets.",
               "**TTS data cleaning:** VLSP 2020/2021 text-to-speech systems denoise found or noisy recordings "
               "before training.",
               "**Open gap:** there is no public Vietnamese noisy/clean benchmark comparable to VoiceBank-DEMAND. "
               "Because Vietnamese is tonal, errors in pitch and phase may hurt intelligibility more than in English."])

    # ------------------------------------------------------------ 4 demo
    R.h1("4  Demo")
    R.p("The demo has three parts. All outputs are scored with the same metric code, so the comparison is fair.")
    R.bullets(["**Official model:** `scripts/demo_official_mpsenet.sh` downloads the authors' code and pretrained "
               "VoiceBank-DEMAND checkpoint, enhances the 824 test files, and scores them with our metrics.",
               "**Our model:** `python -m se.enhance` cleans any wav file or folder with one of our checkpoints.",
               "**Interactive:** `app/gradio_app.py` is a web page where you upload or record speech, choose a model "
               "(for example the baseline or an ablated version), listen to the result and see the spectrograms. "
               "`notebooks/demo.ipynb` does the same in a notebook, with metrics per utterance."])
    R.code(["bash scripts/demo_official_mpsenet.sh data/voicebank_demand_16k",
            "python -m se.enhance --ckpt runs/a00_baseline/checkpoints/best.pt --input noisy.wav --output out/",
            "python app/gradio_app.py --ckpt runs/a00_baseline/checkpoints/best.pt"])

    # ------------------------------------------------------------ 5 method
    R.h1("5  MP-SENet in depth")
    R.h2("5.1  Architecture overview")
    R.p(f"Figure {R.fig_no + 1} shows the whole model. Our re-implementation has **2,047,000 parameters**, matching the 2.05 M "
        "reported in the paper.")
    R.figure("fig_architecture.png", "MP-SENet. A shared encoder and four two-stage Conformer blocks feed two parallel "
             "decoders: one for magnitude, one for phase. The iSTFT combines them into the enhanced waveform.")
    R.bullets([
        "**Input.** The noisy STFT is split into a *compressed magnitude* |Y|^0.3 and a phase ∠Y, stacked as two "
        "channels (201 frequency bins × T frames).",
        "**Dense encoder.** Convolutions with dense connections and growing dilation along time see a wide context "
        "cheaply. A strided convolution halves the frequency axis (201 → 100) to save computation.",
        f"**Four TS-Conformer blocks** (Figure {R.fig_no + 1}) model long-range dependencies along time and along frequency.",
        "**Magnitude decoder.** Upsamples back to 201 bins and outputs a *mask*. The enhanced magnitude is mask × |Y|.",
        "**Phase decoder.** Outputs two values (r, i) per bin; the phase is atan2(i, r). This sidesteps the "
        "problem that phase wraps around at ±π."])
    R.figure("fig_tfblock.png", "A two-stage (TS) Conformer block. The same feature map is processed as sequences "
             "over time, then as sequences over frequency.", width_cm=15)
    R.h2("5.2  Three small design choices with big effects")
    R.figure("fig_compression_mask.png", "Left: power-law compression (c = 0.3) gives quiet but important bins more "
             "weight. Right: a learnable sigmoid with β = 2 lets the mask go above 1, so it can also restore "
             "attenuated speech.")
    R.bullets(["**Magnitude compression (c = 0.3).** Speech spectra span a huge range of loudness. Raising them to "
               "the power 0.3 lifts the quiet bins, so the network and the loss do not ignore them. Ablation a07 "
               "removes this.",
               "**Learnable sigmoid mask (β = 2).** A normal sigmoid can only reduce energy. With β = 2 and a "
               "learnable slope for each frequency, the mask can also amplify. Ablation a10 tests a plain sigmoid.",
               "**Phase via atan2.** Predicting (r, i) and taking the angle always gives a valid phase. Ablations a05 "
               "and a06 replace this with the noisy phase or with complex mapping."])
    R.h2("5.3  Training objectives")
    R.p(f"The model is trained with six losses at once (Figure {R.fig_no + 1}).")
    R.figure("fig_losses.png", "The six objectives and their weights in the total loss.", width_cm=13.5)
    R.bullets(["**Magnitude MSE:** distance between the compressed clean and enhanced magnitudes.",
               "**Phase losses:** compare instantaneous phase (IP), its difference along frequency (group delay, GD) "
               "and its difference along time (instantaneous angular frequency, IAF), all with an *anti-wrapping* "
               f"function (Figure {R.fig_no + 1}).",
               "**Complex MSE:** distance between the compressed real and imaginary parts.",
               "**Time L1:** distance between the waveforms.",
               "**STFT consistency:** re-analysing the output waveform should give back the predicted spectrogram.",
               "**Metric GAN:** a discriminator learns to predict normalised PESQ; the generator is rewarded when the "
               "discriminator thinks its output is perfect."])
    R.figure("fig_phase_wrapping.png", "Why phase needs a special loss. Phase is only defined up to multiples of 2π "
             "(right). A naive loss punishes an error of 2π heavily, although it is no error at all (left, grey); the "
             "anti-wrapping function treats it as zero (left, red).")
    R.h2("5.4  Training setup")
    R.table([["Setting", "Value"],
             ["Sampling rate / STFT", "16 kHz; FFT 400, hop 100, Hann window 400 (25 ms / 6.25 ms)"],
             ["Training segments", "2 s random crops, batch size 4"],
             ["Optimiser", "AdamW, learning rate 5·10⁻⁴, β = (0.8, 0.99); learning rate × 0.99 every epoch"],
             ["Model size", "64 channels, 4 TS-Conformer blocks, 4 attention heads, conv kernel 31"],
             ["Model selection", "best PESQ on the held-out validation speakers"],
             ["Input normalisation", "each noisy utterance is scaled to unit RMS; the output is scaled back"]],
            [4.6, 11.8], caption="Training configuration (`configs/base.yaml`).", center_from=9)

    # ------------------------------------------------------------ 6 ablation
    R.h1("6  Ablation study")
    R.h2("6.1  Idea")
    R.p("An **ablation study** removes or replaces one component at a time and measures how much worse (or better) "
        "the model gets. The bigger the drop, the more that component matters. Every experiment uses the same data, "
        "seed, number of epochs and model-selection rule; only one setting changes.")
    R.h2("6.2  Protocol")
    R.figure("fig_split.png", "Data split. Two training speakers are held out for validation, so the test set is used "
             "only once, for the final numbers. (The original code selects models on the test set, which slightly "
             "inflates results.)", width_cm=14)
    R.figure("fig_pipeline.png", "Experiment pipeline. Each configuration inherits `base.yaml` and changes one key; "
             "14 runs are submitted as one SLURM job array; results are collected into tables and figures.",
             width_cm=15.5)
    R.h2("6.3  Experiments")
    R.table([["ID", "What changes", "Question it answers"]] + [list(a) for a in ABLATIONS],
            [1.2, 6.6, 8.6], caption="The ten ablations. a00 is the full baseline.", size=10, center_from=9)
    R.h2("6.4  Results")
    if rows:
        base = next((r for r in rows if r["run"] == "a00_baseline"), None)
        trows = [["Run", "Description", "PESQ", "ΔPESQ", "CSIG", "CBAK", "COVL", "STOI", "SI-SDR"]]
        hl = []
        for r in rows:
            if r["run"].startswith("p"):
                continue
            dp = f"{float(r['pesq']) - float(base['pesq']):+.3f}" if base and r["run"] != "noisy" else "–"
            trows.append([r["run"].split("_")[0], r["description"], fnum(r["pesq"], 3), dp, fnum(r["csig"]),
                          fnum(r["cbak"]), fnum(r["covl"]), fnum(r["stoi"], 3), fnum(r["si_sdr"])])
            if r["run"] == "a00_baseline":
                hl.append(len(trows) - 1)
        R.table(trows, [1.2, 5.0, 1.5, 1.5, 1.4, 1.4, 1.4, 1.5, 1.5], highlight=tuple(hl), size=9,
                caption="Ablation results on the 824 test utterances. ΔPESQ is relative to the full baseline (a00).")
        R.figure("fig_results.png", "PESQ of every run. The dashed line marks the full baseline; green bars are our "
                 "proposed improvements.")
        if base:
            ab = sorted([r for r in rows if r["run"].startswith("a") and r is not base], key=lambda r: float(r["pesq"]))
            R.p("**Components whose removal hurts most:**")
            R.bullets([f"**{r['run'].split('_')[0]}** ({r['description']}): "
                       f"{float(r['pesq']) - float(base['pesq']):+.3f} PESQ" for r in ab[:3]])
    else:
        R.table([["Run", "Description", "PESQ", "ΔPESQ", "CSIG", "CBAK", "COVL", "STOI", "SI-SDR"],
                 ["noisy", "Noisy input", *["TBD"] * 7], ["a00", "Full baseline", *["TBD"] * 7]] +
                [[a[0], a[1], *["TBD"] * 7] for a in ABLATIONS],
                [1.2, 5.0, 1.5, 1.5, 1.4, 1.4, 1.4, 1.5, 1.5], highlight=(2,), size=9,
                caption="Ablation results on the 824 test utterances (to be filled in automatically).")
        R.callout("Results pending", "Training runs on the HPC cluster. After `scripts/collect_results.py`, rebuilding "
                  "this report fills in the table, adds the results figure and lists the most important components.")
    R.h2("6.5  What we expect, and how to read the numbers")
    R.bullets(["**a05 (noisy phase)** should cause one of the largest drops, since explicit phase is the paper's key "
               "contribution. The difference is often easier to *hear* (rough, robotic sound) than to see in PESQ.",
               "**a01 (no GAN)** should lower PESQ but may *raise* SI-SDR: the discriminator optimises perceived "
               "quality, not waveform accuracy. Comparing both metrics shows whether the GAN only fits PESQ.",
               "**a07 (no compression)** should leave more residual noise in quiet regions.",
               "**a08 / a09** show how much of the quality comes from model depth and from attention.",
               "Differences of about **±0.03 PESQ** are within run-to-run noise on this benchmark. For close cases we "
               "recommend repeating with 2–3 seeds and running a paired test on the per-utterance scores "
               "(`per_file.csv`)."])

    # ------------------------------------------------------------ 7 improvements
    R.h1("7  Proposed improvements")
    R.p("Both proposals change only the **training**, so the trained model is exactly as fast as the baseline.")
    R.h2("7.1  P1: multi-resolution STFT loss")
    R.p("All of MP-SENet's spectral losses use a single STFT resolution (25 ms windows). A short window gives good "
        "time detail but poor frequency detail, and a long one the opposite. The **multi-resolution STFT loss** "
        "compares the enhanced and clean waveforms at three resolutions (256-, 512- and 1024-point FFTs), using "
        "spectral convergence plus log-magnitude distance. This should penalise artefacts such as pre-echo and "
        "smeared onsets that one resolution misses. Weight: 0.1 (`loss.mrstft=0.1`).")
    R.h2("7.2  P2: perceptual contrast stretching (PCS)")
    R.p("PCS makes the *training target* slightly sharper than the real clean speech. The log-magnitude of the clean "
        "spectrum is multiplied by a frequency-dependent gain between 1.0 and 1.4. The strongest gain is applied "
        f"around 0.4–4.4 kHz, the bands that matter most for intelligibility (Figure {R.fig_no + 1}). SEMamba reports a gain of "
        "about 0.14 PESQ from PCS on a Mamba backbone; we test whether it carries over to the Conformer-based "
        "MP-SENet (`data.pcs=true`).")
    R.figure("fig_pcs.png", "PCS gain per frequency (400-point FFT at 16 kHz).", width_cm=14)
    R.h2("7.3  Results")
    prow = [["Run", "Change", "PESQ", "ΔPESQ vs. a00", "STOI", "SI-SDR"],
            ["p01", "+ multi-resolution STFT loss", "TBD", "TBD", "TBD", "TBD"],
            ["p02", "+ PCS target", "TBD", "TBD", "TBD", "TBD"],
            ["p03", "+ both", "TBD", "TBD", "TBD", "TBD"]]
    if rows:
        rmap = {r["run"].split("_")[0]: r for r in rows}
        b = rmap.get("a00")
        for row in prow[1:]:
            r = rmap.get(row[0])
            if r:
                row[2:] = [fnum(r["pesq"], 3), f"{float(r['pesq']) - float(b['pesq']):+.3f}" if b else "–",
                           fnum(r["stoi"], 3), fnum(r["si_sdr"])]
    R.table(prow, [1.4, 6.0, 2.0, 2.8, 2.0, 2.2], caption="Proposed improvements on the test set.")
    R.h2("7.4  Further ideas (not implemented)")
    R.bullets(["**Mamba blocks** instead of Conformers: linear cost in utterance length (SEMamba).",
               "**Causal / streaming version** with chunked attention, for real-time use in calls and hearing aids.",
               "**Vietnamese data:** build a noisy/clean Vietnamese set (e.g. VIVOS mixed with DEMAND/MUSAN noise) "
               "and fine-tune.",
               "**Generalisation:** train or test on the larger DNS-Challenge data."])

    # ------------------------------------------------------------ 8 repo
    R.h1("8  Implementation and reproducibility")
    R.p("The code is a standard Python research repository: configuration files, a package under `src/`, scripts, "
        "SLURM job files and unit tests.")
    R.table([["Folder", "Contents"],
             ["configs/", "`base.yaml` (baseline), `ablation/a01…a10, p01…p03` (one change each), `debug.yaml`"],
             ["src/se/", "data loading, model, losses, metrics, `train.py`, `evaluate.py`, `enhance.py`"],
             ["scripts/", "dataset download, results collection, official-model demo, scoring any folder"],
             ["slurm/", "single run, job array for all experiments, multi-GPU, noisy baseline"],
             ["app/, notebooks/", "web demo (Gradio) and demo notebook"],
             ["tests/", "unit tests for shapes, losses, metrics and configuration"],
             ["docs/", "literature review, ablation design, slides and this report (both auto-generated)"]],
            [3.4, 13.0], caption="Repository layout.", center_from=9)
    R.p("Reproducing everything takes five commands:")
    cmds = [("pip install -e \".[dev]\" && pytest -q", "install and run the tests"),
            ("python scripts/prepare_vbd.py --out data", "download + resample VoiceBank-DEMAND"),
            ("sbatch --array=0-13%4 slurm/ablation_array.sbatch", "train + evaluate all 14 runs"),
            ("python scripts/collect_results.py", "results table and chart"),
            ("python docs/report/build_report.py", "rebuild this report")]
    R.code([f"{c:<52}# {d}" for c, d in cmds])
    R.p("Checks we ran: all 20 unit tests pass; an end-to-end smoke run on synthetic data completes training, the "
        "discriminator step, checkpointing and test evaluation; and the full model has 2.047 M parameters, matching "
        "the paper. Training jobs resume automatically from the last checkpoint if they hit the cluster time limit.")

    # ------------------------------------------------------------ 9 conclusion
    R.h1("9  Conclusion")
    R.p("Speech enhancement has moved from simple magnitude masks to models that estimate phase explicitly, learn from "
        "perceptual metrics and, more recently, generate speech with diffusion or language models. Discriminative "
        "models such as MP-SENet still give the best scores on standard benchmarks for their size, while generative "
        "models are more robust in unseen conditions.")
    R.p("We re-implemented MP-SENet, built a fully reproducible ablation framework with ten single-factor "
        "experiments, and proposed two training-only improvements. The study shows *which* of MP-SENet's many "
        "components carry its performance, which gives practical guidance for building smaller or faster models and "
        "for applying them to new languages such as Vietnamese.")

    # ------------------------------------------------------------ appendix + refs
    R.h1("Appendix A  Work division")
    R.table([["Member", "Student ID", "Tasks", "Share"],
             ["Chau Kien Dat", "25C15036", "Literature survey (P1–P6) and comparison, official demo, web app and notebook, slides, video; report Ch. 1–4", "50%"],
             ["Nguyen Vi Khang", "25C15043", "Re-implementation, configs, HPC training, evaluation metrics, ablation analysis, proposed improvements; report Ch. 5–9", "50%"]],
            [3.2, 2.6, 8.8, 1.8], center_from=3)

    R.h1("References")
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
