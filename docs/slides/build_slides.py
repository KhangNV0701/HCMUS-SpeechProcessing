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
    text(slide, 0.6, H - 0.42, 8, 0.3, "Speech Enhancement · Final project · Speech Processing", size=10,
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
        panels = [("Noisy", noisy), ("Clean", clean)]
        enh = ROOT / "runs" / "a00_baseline" / "eval" / "wavs" / "p232_001.wav"
        if enh.exists():
            e, _ = sf.read(enh)
            panels.insert(1, ("Enhanced (ours)", e))
        caption = "VoiceBank-DEMAND test utterance p232_001"
    else:
        rng = np.random.default_rng(3)
        t = np.arange(int(2.2 * sr)) / sr
        f0 = 140 + 25 * np.sin(2 * np.pi * 1.3 * t)
        ph = 2 * np.pi * np.cumsum(f0) / sr
        env = np.clip(np.sin(2 * np.pi * 2.2 * t) + 0.3, 0, None)
        clean = sum(np.sin(k * ph) / k for k in range(1, 25)) * env * 0.1
        babble = np.convolve(rng.standard_normal(len(t)), np.ones(6) / 6, "same")
        noisy = clean + 0.05 * babble + 0.02 * np.sin(2 * np.pi * 50 * t)
        panels = [("Noisy", noisy), ("Clean", clean)]
        caption = "Illustration (synthetic signal)"
    fig, axes = plt.subplots(1, len(panels), figsize=(4.1 * len(panels), 2.9), sharey=True)
    for ax, (name, x) in zip(np.atleast_1d(axes), panels):
        ax.specgram(np.asarray(x) + 1e-9, NFFT=400, Fs=sr, noverlap=300, cmap="magma", vmin=-130)
        ax.set_title(name, fontsize=12)
        ax.set_xlabel("time (s)")
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
    text(s, 0.8, 1.6, 9.5, 0.5, "SPEECH PROCESSING · FINAL PROJECT · RESEARCH TRACK", size=14, color=AMBER, bold=True)
    text(s, 0.8, 2.15, 11.5, 1.9, ["Speech Enhancement:", "survey and ablation study of MP-SENet"], size=44,
         bold=True, font=HEAD, color=WHITE, spacing=0)
    text(s, 0.8, 4.25, 11, 0.5, "What really matters in a state-of-the-art magnitude–phase denoiser?", size=20,
         italic=True, color="D9CFE0")
    text(s, 0.8, 5.35, 11, 1.0, ["Chau Kien Dat (25C15036)   ·   Nguyen Vi Khang (25C15043)",
                                 "Instructor: <instructor>   ·   HCMUS, Master's program   ·   2026"],
         size=14, color="A79DB0")
    for i, c in enumerate([PLUM, MAGENTA, CORAL, AMBER]):
        badge(s, 11.0 + 0.42 * i, 1.55, "", fill=c, d=0.3)
    s.notes_slide.notes_text_frame.text = (
        "Introduce the group and the topic: single-channel speech enhancement. We survey recent work, run the "
        "official MP-SENet demo, re-implement it and run a one-factor-at-a-time ablation study plus two proposed "
        "improvements.")

    # 2 ── agenda --------------------------------------------------------
    s = new()
    title(s, "Agenda", "The four parts of the assignment")
    items = [("1", "Literature survey", "6 papers, 2023–2025, Q1 / A / A* venues: methods, pros & cons", "30%", PLUM),
             ("2", "Demo", "Official MP-SENet checkpoint and our re-implementation, scored by one metric suite", "20%", MAGENTA),
             ("3", "Ablation study", "10 one-factor ablations of MP-SENet on VoiceBank-DEMAND", "30%", CORAL),
             ("4", "In-depth analysis & improvement", "MR-STFT loss and perceptual contrast stretching", "20%", AMBER)]
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
    title(s, "The problem: recover clean speech from noise", "Single-channel (monaural) speech enhancement")
    png, cap = spectrogram_png(data_root)
    s.shapes.add_picture(io.BytesIO(png), Inches(0.6), Inches(1.75), width=Inches(7.6))
    text(s, 0.6, 1.75 + 7.6 * 2.9 / 8.2 + 0.05, 7.6, 0.3, cap, size=10, color=MUTED, italic=True)
    box(s, 8.6, 1.75, 4.15, 1.25, fill=PLUM)
    text(s, 8.85, 1.85, 3.7, 1.05, [[("y(t) = s(t) + n(t)", {"size": 26, "bold": True, "color": WHITE, "font": HEAD})],
                                    [("estimate ŝ from y only (no reference)", {"size": 13, "color": "E6DDEB"})]],
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 8.6, 3.25, 4.15, 2.0, [
        [("Why it matters", {"bold": True, "size": 16})],
        "• Front-end for ASR, speaker ID, hearing aids",
        "• Calls & meetings: noise destroys intelligibility",
        "• TTS data cleaning (e.g. VLSP corpora)"], size=14)
    text(s, 8.6, 5.15, 4.15, 1.6, [
        [("How it is measured (VoiceBank-DEMAND)", {"bold": True, "size": 16})],
        "• PESQ (1–4.5), STOI (0–1): quality, intelligibility",
        "• CSIG / CBAK / COVL (1–5): MOS predictors",
        "• SSNR, SI-SDR (dB): signal fidelity"], size=14)
    footer(s, n)
    s.notes_slide.notes_text_frame.text = (
        "Define the task. Noise fills the gaps between harmonics in the spectrogram. Introduce the benchmark "
        "(VoiceBank-DEMAND: 11,572 training / 824 test pairs, 16 kHz) and the metrics used in every paper.")

    # 4 ── landscape -----------------------------------------------------
    s = new()
    title(s, "How the world solves it today: three families", "2021 → 2025: from masks to generative and language models")
    fams = [("Discriminative T-F", "Predict a mask / spectrum from the STFT",
             ["MetricGAN+, CMGAN, MP-SENet", "SEMamba, DeepFilterNet"],
             "+ best PESQ, ~2 M params, fast", "− artefacts, phase is hard, domain shift", PLUM),
            ("Generative: diffusion", "Learn p(clean | noisy), then sample",
             ["SGMSE+, StoRM, DOSE"], "+ natural, robust to unseen noise",
             "− many steps (slow), hallucination", MAGENTA),
            ("Language-model / tokens", "Predict clean codec / SSL tokens with an LM",
             ["SELM, MaskSR, GenSE"], "+ real-world, multi-distortion",
             "− huge, slow, content / speaker drift", CORAL)]
    for i, (h, d, ex, pro, con, c) in enumerate(fams):
        x = 0.6 + i * 4.1
        box(s, x, 1.8, 3.85, 4.15, fill=TINT)
        badge(s, x + 0.3, 2.05, str(i + 1), fill=c, d=0.55, size=18)
        text(s, x + 1.0, 2.07, 2.7, 0.55, h, size=19, bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 0.3, 2.8, 3.3, 0.7, d, size=14, color=MUTED, italic=True)
        text(s, x + 0.3, 3.5, 3.3, 0.9, ["• " + e for e in ex], size=14)
        text(s, x + 0.3, 4.55, 3.3, 1.3, [[(pro, {"color": GOOD, "bold": True})], [(con, {"color": CORAL, "bold": True})]],
             size=14)
    text(s, 0.6, 6.15, 12.1, 0.7, [[("Trends: ", {"bold": True, "color": MAGENTA}),
                                    ("explicit phase modelling · metric-driven (PESQ) training · time + frequency "
                                     "sequence modelling (Conformer → Mamba) · generative robustness · real-time designs", {})]],
         size=14)
    footer(s, n)

    # 5-8 ── papers ------------------------------------------------------
    papers = [
        ("CMGAN: Conformer-based Metric GAN", "Abdulatif, Cao, Yang · IEEE/ACM TASLP 2024 (Q1)",
         ["Dense encoder → 4 two-stage (time, freq) Conformers",
          "Mask decoder for magnitude + complex decoder refining real/imag",
          "MetricGAN discriminator learns PESQ → generator maximises it"],
         ["Strong results with 1.83 M params", "TF-Conformer captures long time & frequency context",
          "Thorough: denoising, dereverberation, super-resolution"],
         ["Phase only refined implicitly", "Quadratic attention, non-causal",
          "PESQ in the training loop is slow"],
         ("3.41", "PESQ on VB-D")),
        ("MP-SENet: parallel magnitude & phase", "Lu, Ai, Ling · Interspeech 2023 (CORE A); extended in Neural Networks 2025",
         ["Same backbone, two parallel decoders: magnitude mask + explicit phase",
          "Phase decoder predicts (r, i) → atan2 gives a wrap-free phase",
          "Anti-wrapping losses: instantaneous phase, group delay, inst. frequency"],
         ["SOTA among ~2 M-param models", "First explicit phase estimation that works",
          "Official code + checkpoints"],
         ["6 loss terms, hand-tuned weights", "Non-causal; trained on VB-D noise only",
          "Metric GAN can over-fit PESQ"],
         ("3.50", "PESQ on VB-D")),
        ("SGMSE+ and StoRM: diffusion for SE", "Richter et al. & Lemercier et al. · IEEE/ACM TASLP 2023 (Q1)",
         ["SGMSE+: SDE drifting clean → noisy; reverse with predictor–corrector",
          "Score network NCSN++ in the complex STFT domain",
          "StoRM: predictive model first, diffusion regenerates the details"],
         ["Natural output, best on mismatched data", "Same model dereverberates",
          "StoRM: no breathing artefacts, fewer steps"],
         ["~60 network calls / utterance (SGMSE+)", "Hallucination at low SNR",
          "PESQ below the discriminative SOTA"],
         ("2.93", "PESQ on VB-D (SGMSE+)")),
        ("DOSE and GenSE: efficient & token-based generation", "Tai et al. · NeurIPS 2023 (A*) — Yao et al. · ICLR 2025 (A*)",
         ["DOSE: diffusion dropout + adaptive prior → only 2 sampling steps",
          "GenSE: SE as language modelling on SSL semantic + codec tokens",
          "Hierarchical: noisy → clean semantic → acoustic, keeps timbre"],
         ["DOSE: fast diffusion, good generalisation", "GenSE: robust on real recordings",
          "One model for many distortions"],
         ["Lower PESQ than discriminative models", "GenSE: large, autoregressive decoding",
          "Content / speaker drift risk"],
         ("2", "sampling steps (DOSE)")),
    ]
    for k, (h, venue, method, pros, cons, stat) in enumerate(papers):
        s = new()
        title(s, h, venue)
        box(s, 0.6, 1.8, 7.9, 2.05, fill=TINT)
        text(s, 0.85, 1.95, 7.4, 0.4, "Method", size=16, bold=True, color=MAGENTA)
        text(s, 0.85, 2.35, 7.4, 1.5, ["• " + m for m in method], size=15)
        box(s, 0.6, 4.05, 3.85, 2.6, fill=WHITE, line=LINE)
        text(s, 0.85, 4.2, 3.4, 0.4, "Strengths", size=16, bold=True, color=GOOD)
        text(s, 0.85, 4.6, 3.4, 2.0, ["• " + p for p in pros], size=14)
        box(s, 4.65, 4.05, 3.85, 2.6, fill=WHITE, line=LINE)
        text(s, 4.9, 4.2, 3.4, 0.4, "Weaknesses", size=16, bold=True, color=CORAL)
        text(s, 4.9, 4.6, 3.4, 2.0, ["• " + c for c in cons], size=14)
        box(s, 8.9, 1.8, 3.85, 4.85, fill=PLUM)
        text(s, 9.1, 2.6, 3.45, 1.5, stat[0], size=72, bold=True, font=HEAD, color=AMBER, align=PP_ALIGN.CENTER)
        text(s, 9.1, 4.1, 3.45, 0.5, stat[1], size=16, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, 9.1, 5.6, 3.45, 0.7, "as reported by the authors", size=12, italic=True, color="CDBFD6",
             align=PP_ALIGN.CENTER)
        footer(s, n)

    # 9 ── comparison ----------------------------------------------------
    s = new()
    title(s, "Side by side on VoiceBank-DEMAND", "Reported PESQ (wb) — discriminative models lead on intrusive metrics")
    cats = ["Noisy input", "SGMSE+ (TASLP'23)", "MetricGAN+ (IS'21)", "CMGAN (TASLP'24)", "MP-SENet (IS'23)",
            "SEMamba + PCS (SLT'24)"]
    vals = [1.97, 2.93, 3.15, 3.41, 3.50, 3.69]
    bar_chart(s, 0.6, 1.7, 7.0, 4.9, cats, vals, "PESQ on VB-D test set (reported)",
              colors=["B9AEC2", MAGENTA, PLUM, PLUM, CORAL, AMBER], vmin=1.0, vmax=4.0)
    rows = [["Model", "Type", "Params", "Steps"],
            ["MetricGAN+", "mask + metric GAN", "–", "1"],
            ["CMGAN", "mag + complex", "1.83 M", "1"],
            ["MP-SENet", "mag + phase", "2.05 M", "1"],
            ["SGMSE+", "diffusion", "~65 M", "~60"],
            ["DOSE", "diffusion", "–", "2"],
            ["GenSE", "LM on tokens", "large", "AR"]]
    table(s, 7.9, 1.85, 4.85, rows, col_w=[1.35, 1.6, 0.95, 0.95], size=12, row_h=0.42, highlight_rows=(3,))
    text(s, 7.9, 5.0, 4.85, 1.5, ["Generative models score lower on PESQ but generalise better and sound more natural.",
                                  "We choose MP-SENet: best accuracy per parameter, official code, and the base of later work."],
         size=13, color=MUTED)
    footer(s, n)

    # 10 ── Vietnam ------------------------------------------------------
    s = new()
    title(s, "In Vietnam: noise is handled downstream", "Few dedicated SE papers in Q1/Q2 or A/A* venues")
    cards = [("ASR robustness", "Noise-augmented training for Vietnamese ASR, e.g. 2,000 h of real Vietnamese noise "
                                "mixed into a 200 h corpus (Tạp chí Khoa học, 2025)."),
             ("TTS data cleaning", "VLSP 2020/2021 TTS systems denoise found or noisy recordings before training."),
             ("Open gap", "No public VB-D-style Vietnamese SE benchmark; tonal language → phase/pitch errors matter more.")]
    for i, (h, d) in enumerate(cards):
        y = 1.8 + i * 1.62
        box(s, 0.6, y, 7.6, 1.4, fill=TINT)
        badge(s, 0.85, y + 0.42, str(i + 1), fill=[PLUM, MAGENTA, CORAL][i], d=0.55, size=18)
        text(s, 1.65, y + 0.15, 6.35, 0.4, h, size=17, bold=True, font=HEAD)
        text(s, 1.65, y + 0.55, 6.35, 0.85, d, size=14, color=MUTED)
    box(s, 8.6, 1.8, 4.15, 4.64, fill=PLUM)
    text(s, 8.9, 2.05, 3.6, 4.2, [[("Opportunity", {"bold": True, "size": 20, "color": AMBER, "font": HEAD})],
                                  [("A small explicit-phase model such as MP-SENet is a good candidate front-end for "
                                    "Vietnamese ASR / TTS pipelines.", {"color": WHITE, "size": 15})],
                                  [("Next step: build a Vietnamese noisy–clean set (e.g. VIVOS + DEMAND / MUSAN) "
                                    "and fine-tune.", {"color": "E6DDEB", "size": 15})]], spacing=12)
    footer(s, n)

    # 11 ── demo ---------------------------------------------------------
    s = new()
    title(s, "Demo: official model and our pipeline", "Everything is scored with the same metric suite")
    steps = [("Prepare", "prepare_vbd.py\n48 → 16 kHz"), ("Official", "MP-SENet\npretrained ckpt"),
             ("Ours", "se.train / se.enhance"), ("Score", "PESQ, STOI, CSIG…\nscore_dir.py"),
             ("Listen", "demo.ipynb\nablation runs")]
    for i, (h, d) in enumerate(steps):
        x = 0.6 + i * 2.5
        box(s, x, 1.9, 2.1, 1.75, fill=TINT)
        badge(s, x + 0.2, 2.05, str(i + 1), fill=[PLUM, MAGENTA, CORAL, AMBER, PLUM][i], d=0.45, size=15)
        text(s, x + 0.75, 2.05, 1.3, 0.45, h, size=16, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 0.2, 2.65, 1.8, 0.95, d, size=13, color=MUTED)
        if i < len(steps) - 1:
            arrow(s, x + 2.12, 2.78, x + 2.48, 2.78)
    code = ("bash scripts/demo_official_mpsenet.sh data/voicebank_demand_16k\n"
            "python -m se.enhance --ckpt runs/a00_baseline/checkpoints/best.pt --input noisy.wav --output out/\n"
            "jupyter notebook notebooks/demo.ipynb   # listen to baseline vs ablated runs")
    box(s, 0.6, 4.0, 12.15, 1.45, fill=INK)
    text(s, 0.85, 4.12, 11.7, 1.25, code.split("\n"), size=13, font="Courier New", color="F3E9F7")
    text(s, 0.6, 5.7, 12.15, 0.9, [[("In the video: ", {"bold": True, "color": MAGENTA}),
                                    ("run the official checkpoint on test files, then play the same utterance through the baseline "
                                     "and ablated checkpoints and compare spectrograms and PESQ / STOI.", {})]], size=15)
    footer(s, n)

    # 12 ── architecture -------------------------------------------------
    s = new()
    title(s, "The chosen solution: MP-SENet in depth", "Our re-implementation has 2.047 M parameters (paper: 2.05 M)")
    # input
    box(s, 0.6, 3.1, 1.9, 1.3, fill=TINT)
    text(s, 0.7, 3.15, 1.7, 1.2, [[("Noisy STFT", {"bold": True})], "|Y|^0.3 and ∠Y", "201 bins × T"], size=13,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 2.52, 3.75, 2.9, 3.75)
    box(s, 2.9, 3.0, 2.0, 1.5, fill=PLUM)
    text(s, 3.0, 3.05, 1.8, 1.4, [[("Dense encoder", {"bold": True, "color": WHITE})],
                                  [("dilated DenseBlock, freq ↓2", {"color": "E6DDEB", "size": 12})]], size=14,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 4.92, 3.75, 5.3, 3.75)
    box(s, 5.3, 2.75, 2.5, 2.0, fill=MAGENTA)
    text(s, 5.4, 2.8, 2.3, 1.9, [[("4 × TS-Conformer", {"bold": True, "color": WHITE})],
                                 [("time-Conformer → freq-Conformer", {"color": "FCE7F1", "size": 12})],
                                 [("MHSA + conv + FFN", {"color": "FCE7F1", "size": 12})]], size=15,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 7.82, 3.4, 8.3, 2.5)
    arrow(s, 7.82, 4.1, 8.3, 5.0)
    box(s, 8.3, 1.85, 2.4, 1.3, fill=CORAL)
    text(s, 8.4, 1.9, 2.2, 1.2, [[("Magnitude decoder", {"bold": True, "color": WHITE})],
                                 [("mask = 2·σ(a_f · x) → mask·|Y|", {"color": WHITE, "size": 12})]], size=14,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    box(s, 8.3, 4.35, 2.4, 1.3, fill=AMBER)
    text(s, 8.4, 4.4, 2.2, 1.2, [[("Phase decoder", {"bold": True})],
                                 [("(r, i) → atan2(i, r)", {"size": 12})]], size=14, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE)
    arrow(s, 10.72, 2.5, 11.15, 3.4)
    arrow(s, 10.72, 5.0, 11.15, 4.1)
    box(s, 11.15, 3.1, 1.6, 1.3, fill=TINT)
    text(s, 11.2, 3.15, 1.5, 1.2, [[("iSTFT", {"bold": True})], "enhanced ŝ"], size=14, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.6, 5.95, 12.15, 0.9, [[("Key idea: ", {"bold": True, "color": MAGENTA}),
                                     ("phase is predicted explicitly and in parallel with magnitude. Predicting a "
                                      "pseudo real/imag pair and taking atan2 avoids regressing a wrapped angle.", {})]],
         size=15)
    footer(s, n)

    # 13 ── losses -------------------------------------------------------
    s = new()
    title(s, "Six training objectives, each one ablated", "L = 0.9 L_mag + 0.3 L_pha + 0.1 L_com + 0.2 L_time + 0.1 L_cons + 0.05 L_metric")
    losses = [("Magnitude", "MSE on compressed |S|^0.3", "0.9"),
              ("Phase (anti-wrapping)", "IP + group delay + inst. angular freq.; f(x)=|x − 2π·round(x/2π)|", "0.3"),
              ("Complex", "MSE on compressed real / imag", "0.1"),
              ("Time", "L1 on the waveform", "0.2"),
              ("Consistency", "STFT(iSTFT(Ŝ)) ≈ Ŝ", "0.1"),
              ("Metric GAN", "D learns PESQ; G pushes D(ŝ) → 1", "0.05")]
    for i, (h, d, wgt) in enumerate(losses):
        col, row = i % 2, i // 2
        x, y = 0.6 + col * 6.15, 1.85 + row * 1.5
        box(s, x, y, 5.95, 1.3, fill=TINT)
        badge(s, x + 0.25, y + 0.3, wgt, fill=[CORAL, AMBER, MAGENTA, PLUM, PLUM, MAGENTA][i], d=0.7, size=13)
        text(s, x + 1.15, y + 0.15, 4.6, 0.4, h, size=17, bold=True, font=HEAD)
        text(s, x + 1.15, y + 0.55, 4.6, 0.7, d, size=13, color=MUTED)
    text(s, 0.6, 6.4, 12.15, 0.5, "Questions: are all six needed? Which one carries the PESQ gain, and which only fits the metric?",
         size=14, italic=True, color=MAGENTA)
    footer(s, n)

    # 14 ── ablation design ---------------------------------------------
    s = new()
    title(s, "Ablation design: change one factor at a time", "Every config inherits configs/base.yaml and changes exactly one key")
    rows = [["ID", "Change", "Question"],
            ["a01", "no metric discriminator", "Real gain, or PESQ over-fitting?"],
            ["a02", "no phase losses", "Can phase be learned without them?"],
            ["a03", "no consistency loss", "Need a consistent spectrogram?"],
            ["a04", "no time + complex losses", "Value of multi-domain terms"],
            ["a05", "magnitude-only (noisy phase)", "Core claim: explicit phase"],
            ["a06", "complex-mapping decoder", "Parallel mag/phase vs complex"],
            ["a07", "no compression (c = 1)", "Dynamic-range compression"],
            ["a08", "2 TS-Conformer blocks", "Depth vs quality / speed"],
            ["a09", "BiLSTM instead of Conformer", "Attention+conv vs recurrence"],
            ["a10", "plain sigmoid mask (β = 1)", "Can the mask amplify (> 1)?"]]
    table(s, 0.6, 1.75, 8.3, rows, col_w=[0.75, 3.35, 4.2], size=13, row_h=0.43)
    box(s, 9.2, 1.75, 3.55, 4.73, fill=PLUM)
    text(s, 9.45, 1.95, 3.1, 4.4, [[("Protocol", {"bold": True, "size": 20, "color": AMBER, "font": HEAD})],
                                   [("VB-D 16 kHz; p226 & p287 held out for validation", {"color": WHITE})],
                                   [("Test set (824) used once, for final numbers", {"color": WHITE})],
                                   [("Same seed, epochs, selection (best val PESQ)", {"color": WHITE})],
                                   [("PESQ, CSIG, CBAK, COVL, SSNR, STOI, SI-SDR, params, RTF", {"color": WHITE})],
                                   [("14 SLURM array jobs on HPC", {"color": "E6DDEB"})]], size=14, spacing=10)
    footer(s, n)

    # 15 ── results table -----------------------------------------------
    s = new()
    title(s, "Ablation results on the VoiceBank-DEMAND test set",
          "Mean over 824 utterances · Δ = change in PESQ vs. the full baseline (a00)")
    header = ["Run", "Description", "PESQ", "ΔPESQ", "CSIG", "CBAK", "COVL", "STOI", "SI-SDR"]
    if results:
        base = next((r for r in results if r["run"] == "a00_baseline"), None)
        rows = [header]
        hl = []
        for r in results:
            dp = "–"
            if base and r["run"] != "noisy" and r.get("pesq"):
                dp = f"{float(r['pesq']) - float(base['pesq']):+.3f}"
            rows.append([r["run"].split("_")[0], r["description"][:38], fnum(r["pesq"], 3), dp, fnum(r["csig"]),
                         fnum(r["cbak"]), fnum(r["covl"]), fnum(r["stoi"], 3), fnum(r["si_sdr"])])
            if r["run"] == "a00_baseline":
                hl.append(len(rows) - 1)
        rh = min(0.34, 4.9 / len(rows))
        table(s, 0.6, 1.7, 12.15, rows, col_w=[0.8, 4.35, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
              size=11 if len(rows) > 12 else 12, row_h=rh, highlight_rows=tuple(hl))
    else:
        names = ["noisy", "a00", "a01", "a02", "a03", "a04", "a05", "a06", "a07", "a08", "a09", "a10"]
        rows = [header] + [[nm, "", "TBD", "TBD", "TBD", "TBD", "TBD", "TBD", "TBD"] for nm in names]
        desc = {"noisy": "Noisy input (no processing)", "a00": "Full baseline (MP-SENet-style)",
                "a01": "no metric discriminator", "a02": "no phase losses", "a03": "no consistency loss",
                "a04": "no time + complex losses", "a05": "magnitude-only decoder (noisy phase)",
                "a06": "complex-mapping decoder", "a07": "no magnitude compression (c = 1)",
                "a08": "2 TS-Conformer blocks", "a09": "BiLSTM instead of Conformer",
                "a10": "plain sigmoid mask (β = 1)"}
        for row in rows[1:]:
            row[1] = desc[row[0]]
        table(s, 0.6, 1.7, 12.15, rows, col_w=[0.8, 4.35, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], size=12, row_h=0.36,
              highlight_rows=(2,))
        text(s, 0.6, 6.45, 12.15, 0.4, "Results pending: training runs on the HPC cluster. Run "
             "scripts/collect_results.py, then rebuild this deck to fill the table.", size=12, italic=True, color=CORAL)
    footer(s, n)

    # 16 ── results chart + discussion ------------------------------------
    s = new()
    title(s, "What matters most?", "PESQ per run (baseline highlighted) and how to read it")
    if results:
        rr = [r for r in results if r["run"] != "noisy" and r.get("pesq")]
        cats = [r["run"].split("_")[0] for r in rr]
        vals = [float(r["pesq"]) for r in rr]
        cols = [AMBER if r["run"].startswith("a00") else GOOD if r["run"].startswith("p") else PLUM for r in rr]
        bar_chart(s, 0.6, 1.65, 6.9, 5.2, cats, vals, "PESQ (wb) on the test set", colors=cols,
                  vmin=round(min(vals) - 0.2, 1), vmax=round(max(vals) + 0.1, 1), fmt="0.000")
        base = next((r for r in rr if r["run"] == "a00_baseline"), None)
        if base:
            ab = sorted([r for r in rr if r["run"].startswith("a") and r is not base],
                        key=lambda r: float(r["pesq"]))
            worst = ab[:3]
            bullets = [f"• {r['run'].split('_')[0]} ({r['description'][:30]}): "
                       f"{float(r['pesq']) - float(base['pesq']):+.3f} PESQ" for r in worst]
            heads = "Largest drops when removed"
        else:
            bullets, heads = [], "Discussion"
    else:
        box(s, 0.6, 1.75, 6.9, 4.9, fill=TINT)
        text(s, 0.9, 3.6, 6.3, 1.2, [[("Chart appears here after the HPC runs", {"bold": True, "size": 18})],
                                     [("generated from results/ablation_results.csv", {"color": MUTED})]],
             size=15, align=PP_ALIGN.CENTER)
        heads = "Hypotheses to test"
        bullets = ["• a05 (noisy phase) should cost the most: explicit phase is the paper's core claim",
                   "• a01 (no GAN): PESQ drops, but SI-SDR may rise; the GAN tunes for the metric",
                   "• a07 (no compression): quiet bins are under-weighted, so more residual noise",
                   "• a09 (BiLSTM): close in PESQ, but slower, and worse for long context"]
    text(s, 7.85, 1.75, 4.9, 0.5, heads, size=19, bold=True, font=HEAD, color=MAGENTA)
    text(s, 7.85, 2.3, 4.9, 3.2, bullets, size=14, spacing=8)
    box(s, 7.85, 5.35, 4.9, 1.3, fill=PLUM)
    text(s, 8.05, 5.42, 4.5, 1.15, "ΔPESQ around ±0.03 is within seed noise on VB-D: confirm with a paired test on "
         "per_file.csv and listen to the outputs.", size=13, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    footer(s, n)

    # 17 ── proposals -----------------------------------------------------
    s = new()
    title(s, "Proposed improvements", "Both are training-only changes: zero extra inference cost")
    box(s, 0.6, 1.75, 5.9, 2.25, fill=TINT)
    badge(s, 0.85, 1.95, "P1", fill=CORAL, d=0.62, size=15)
    text(s, 1.65, 1.95, 4.7, 0.6, "Multi-resolution STFT loss", size=19, bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.85, 2.65, 5.45, 1.35, ["• All paper losses use one STFT (25 ms window)",
                                     "• Add spectral convergence + log-mag L1 at 256 / 512 / 1024-point FFTs",
                                     "• Targets pre-echo and smeared transients"], size=14)
    box(s, 0.6, 4.2, 5.9, 2.45, fill=TINT)
    badge(s, 0.85, 4.4, "P2", fill=AMBER, d=0.62, size=15)
    text(s, 1.65, 4.4, 4.7, 0.6, "Perceptual contrast stretching", size=19, bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.85, 5.1, 5.45, 1.5, ["• Sharpen the clean target: log1p|S| × g(f), g ∈ [1, 1.4]",
                                   "• Gains follow speech-intelligibility band importance",
                                   "• SEMamba: +0.14 PESQ on Mamba. Does it carry over to Conformer?"], size=14)
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from se.utils.pcs import pcs400_gains  # same table the training code uses
    g = [round(float(v), 3) for v in pcs400_gains(201)]
    xs = [f"{k * 8 / 200:.0f} kHz" if k % 25 == 0 else "" for k in range(201)]
    line_chart(s, 6.85, 1.75, 5.9, 3.3, xs, g, "PCS gain g(f) per frequency bin")
    rows = [["Run", "Change", "PESQ"], ["p01", "+ MR-STFT loss", "TBD"], ["p02", "+ PCS target", "TBD"],
            ["p03", "+ both", "TBD"]]
    if results:
        rmap = {r["run"].split("_")[0]: r for r in results}
        for row in rows[1:]:
            if row[0] in rmap:
                row[2] = fnum(rmap[row[0]]["pesq"], 3)
    table(s, 6.85, 5.25, 5.9, rows, col_w=[1.0, 3.4, 1.5], size=13, row_h=0.35)
    footer(s, n)

    # 18 ── repo ------------------------------------------------------------
    s = new()
    title(s, "Reproducible by design", "Standard AI-repo layout · one command per stage · HPC-ready")
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
    steps = [("Install", "pip install -e \".[dev]\" · pytest -q"),
             ("Data", "python scripts/prepare_vbd.py --out data"),
             ("Train all", "sbatch --array=0-13%4 slurm/ablation_array.sbatch"),
             ("Report", "python scripts/collect_results.py"),
             ("Slides", "python docs/slides/build_slides.py")]
    for i, (h, d) in enumerate(steps):
        y = 1.75 + i * 0.99
        badge(s, 7.55, y + 0.12, str(i + 1), fill=[PLUM, MAGENTA, CORAL, AMBER, PLUM][i], d=0.5, size=15)
        text(s, 8.25, y, 4.5, 0.4, h, size=16, bold=True)
        text(s, 8.25, y + 0.38, 4.5, 0.5, d, size=12, font="Courier New", color=MUTED)
    footer(s, n)

    # 19 ── conclusion ------------------------------------------------------
    s = new(dark=True)
    text(s, 0.8, 0.8, 11, 0.8, "Conclusion & future work", size=36, bold=True, font=HEAD, color=WHITE)
    cols = [("What we did", ["Surveyed 6 recent papers across 3 families",
                             "Ran the official MP-SENet demo",
                             "Re-implemented it (2.05 M params) with 10 ablations",
                             "Proposed MR-STFT loss and PCS target"]),
            ("What we learn", ["Which components carry the gain (results slide)",
                               "Phase modelling vs metric-GAN contribution",
                               "Accuracy vs cost of the TF backbone"]),
            ("Next", ["Mamba blocks for linear-time context",
                      "Causal / streaming variant for real time",
                      "Vietnamese noisy–clean data and fine-tuning",
                      "DNS-Challenge for generalisation"])]
    for i, (h, b) in enumerate(cols):
        x = 0.8 + i * 4.0
        box(s, x, 2.0, 3.7, 4.3, fill=PLUM)
        text(s, x + 0.3, 2.2, 3.1, 0.5, h, size=20, bold=True, color=AMBER, font=HEAD)
        text(s, x + 0.3, 2.85, 3.1, 3.3, [[(t, {"color": WHITE})] for t in b], size=15, spacing=10)
    text(s, 0.8, 6.6, 11, 0.4, "Thank you! Questions?", size=18, italic=True, color="D9CFE0")
    footer(s, n, dark=True)

    # 20 ── team -------------------------------------------------------------
    s = new()
    title(s, "Team and task split")
    rows = [["Member", "Student ID", "Tasks", "Share"],
            ["Chau Kien Dat", "25C15036", "Literature survey, demo, slides, video", "50%"],
            ["Nguyen Vi Khang", "25C15043", "Re-implementation, HPC ablation runs, evaluation, report", "50%"]]
    table(s, 0.6, 1.9, 12.15, rows, col_w=[2.6, 2.0, 6.0, 1.55], size=15, row_h=0.6)
    footer(s, n)

    # 21 ── references -----------------------------------------------------
    s = new()
    title(s, "References")
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
