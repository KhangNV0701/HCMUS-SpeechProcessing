"""Figures for the written report (docs/report/figures/*.png).

    python docs/report/make_figures.py [--results results/ablation_results.csv]

All figures share the "magma" palette used in the slides and spectrograms.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("figures")

INK, PLUM, MAGENTA, CORAL, AMBER = "#1A1423", "#3D1E4F", "#B5367A", "#E8553F", "#F5A524"
TINT, MUTED, GREY, GOOD = "#F5F0F7", "#6B6275", "#B9AEC2", "#2E8B57"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": "#9A90A3",
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
    "axes.titlesize": 12, "savefig.dpi": 220, "savefig.bbox": "tight",
})


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- diagrams
def node(ax, x, y, w, h, label, sub=None, fc=PLUM, tc="white", fs=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fc, ec="none"))
    if sub:
        ax.text(x + w / 2, y + h * 0.62, label, ha="center", va="center", color=tc, fontsize=fs,
                fontweight="bold")
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", color=tc, fontsize=fs - 2.5,
                linespacing=1.3)
    else:
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", color=tc, fontsize=fs,
                fontweight="bold", linespacing=1.3)


def link(ax, p, q, color=MUTED, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, color=color, lw=1.6,
                                 connectionstyle=f"arc3,rad={rad}"))


def canvas(w, h, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


def fig_spectrogram(data_root: Path | None):
    sr = 16000
    real = data_root and (data_root / "clean_testset_wav" / "p232_001.wav").exists()
    if real:
        import soundfile as sf
        clean, _ = sf.read(data_root / "clean_testset_wav" / "p232_001.wav")
        noisy, _ = sf.read(data_root / "noisy_testset_wav" / "p232_001.wav")
    else:
        rng = np.random.default_rng(3)
        t = np.arange(int(2.2 * sr)) / sr
        f0 = 140 + 25 * np.sin(2 * np.pi * 1.3 * t)
        ph = 2 * np.pi * np.cumsum(f0) / sr
        env = np.clip(np.sin(2 * np.pi * 2.2 * t) + 0.3, 0, None)
        clean = sum(np.sin(k * ph) / k for k in range(1, 25)) * env * 0.1
        noisy = clean + 0.05 * np.convolve(rng.standard_normal(len(t)), np.ones(6) / 6, "same")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.0), sharey=True)
    for ax, (name, x) in zip(axes, [("Noisy input  y = s + n", noisy), ("Clean target  s", clean)]):
        ax.specgram(np.asarray(x) + 1e-9, NFFT=400, Fs=sr, noverlap=300, cmap="magma", vmin=-130)
        ax.set_title(name)
        ax.set_xlabel("time (s)")
        ax.set_ylim(0, 8000)
    axes[0].set_ylabel("frequency (Hz)")
    fig.suptitle("VoiceBank-DEMAND utterance p232_001" if real else "Illustration (synthetic voiced signal)",
                 fontsize=10, color=MUTED, y=0.02)
    fig.tight_layout()
    save(fig, "fig_spectrogram.png")


def fig_taxonomy():
    fig, ax = canvas(10, 4.6, (0, 10), (0, 4.6))
    node(ax, 2.9, 3.7, 4.2, 0.7, "Single-channel speech enhancement", fc=INK, fs=11)
    cols = [(0.2, PLUM, "Discriminative (T-F)", "predict a mask or spectrum\nin one forward pass",
             "MetricGAN+ · CMGAN\nMP-SENet · SEMamba\nDeepFilterNet",
             "+ highest PESQ, ~2 M params\n− phase hard, domain shift"),
            (3.5, MAGENTA, "Generative: diffusion", "learn p(clean | noisy)\nand sample from it",
             "SGMSE+ · StoRM · DOSE", "+ natural, robust\n− many steps, hallucination"),
            (6.8, CORAL, "Language-model based", "predict clean discrete\ntokens with an LM",
             "SELM · MaskSR · GenSE", "+ real-world, many distortions\n− large, slow, drift")]
    for x, c, h, d, ex, pc in cols:
        link(ax, (5.0, 3.68), (x + 1.5, 3.05), rad=0.0)
        node(ax, x, 2.35, 3.0, 0.7, h, fc=c, fs=11)
        ax.text(x + 1.5, 1.95, d, ha="center", va="center", fontsize=9.5, color=MUTED, style="italic")
        ax.add_patch(FancyBboxPatch((x, 0.15), 3.0, 1.35, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc=TINT, ec="none"))
        ax.text(x + 1.5, 1.12, ex, ha="center", va="center", fontsize=9.5, color=INK, fontweight="bold")
        ax.text(x + 1.5, 0.45, pc, ha="center", va="center", fontsize=9, color=INK)
    save(fig, "fig_taxonomy.png")


def fig_timeline():
    items = [(2021.3, "MetricGAN+", "Interspeech", PLUM, 1), (2022.2, "DeepFilterNet", "ICASSP", PLUM, -1),
             (2023.1, "SGMSE+ · StoRM", "TASLP", MAGENTA, 1), (2023.6, "MP-SENet", "Interspeech", CORAL, -1),
             (2023.9, "DOSE", "NeurIPS", MAGENTA, 1), (2024.1, "CMGAN", "TASLP", PLUM, -1),
             (2024.9, "SEMamba", "SLT", PLUM, 1), (2025.3, "GenSE", "ICLR", AMBER, -1)]
    fig, ax = plt.subplots(figsize=(9.5, 2.6))
    ax.axhline(0, color=GREY, lw=2, zorder=0)
    for x, name, venue, c, side in items:
        ax.plot([x, x], [0, 0.3 * side], color=c, lw=1.4)
        ax.scatter([x], [0], s=60, color=c, zorder=3)
        ax.text(x, (0.78 if side > 0 else 0.72) * side, name, ha="center", va="center", fontsize=10, fontweight="bold", color=INK)
        ax.text(x, (0.48 if side > 0 else 0.42) * side, venue, ha="center", va="center", fontsize=8.5, color=MUTED)
    ax.set_xlim(2020.8, 2025.8)
    ax.set_ylim(-1.0, 1.15)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([2021, 2022, 2023, 2024, 2025])
    ax.tick_params(axis="x", length=0, labelsize=10)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=PLUM, label="discriminative"),
                       Line2D([], [], marker="o", ls="", color=MAGENTA, label="diffusion"),
                       Line2D([], [], marker="o", ls="", color=AMBER, label="language-model based"),
                       Line2D([], [], marker="o", ls="", color=CORAL, label="chosen model")],
              loc="upper left", fontsize=8.5, frameon=False, ncol=4, bbox_to_anchor=(0, 1.12))
    save(fig, "fig_timeline.png")


def fig_reported_pesq():
    names = ["Noisy input", "SGMSE+ (TASLP'23)", "MetricGAN+ (IS'21)", "CMGAN (TASLP'24)",
             "MP-SENet (IS'23)", "SEMamba+PCS (SLT'24)"]
    vals = [1.97, 2.93, 3.15, 3.41, 3.50, 3.69]
    cols = [GREY, MAGENTA, PLUM, PLUM, CORAL, AMBER]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    y = np.arange(len(names))[::-1]
    ax.barh(y, vals, color=cols, height=0.62)
    for yi, v in zip(y, vals):
        ax.text(v + 0.03, yi, f"{v:.2f}", va="center", fontsize=10, color=INK)
    ax.set_yticks(y, names)
    ax.set_xlim(1, 4.1)
    ax.set_xlabel("PESQ (wide-band), higher is better")
    ax.grid(axis="x", color="#ECE6EF")
    ax.set_axisbelow(True)
    ax.set_title("Reported results on the VoiceBank-DEMAND test set", loc="left")
    save(fig, "fig_reported_pesq.png")


def fig_architecture():
    fig, ax = canvas(11, 4.4, (0, 11), (0, 4.4))
    node(ax, 0.1, 1.55, 1.6, 1.3, "Noisy STFT", "|Y|^0.3  and  ∠Y\n201 bins × T frames", fc=TINT, tc=INK, fs=10.5)
    link(ax, (1.72, 2.2), (2.05, 2.2))
    node(ax, 2.05, 1.45, 1.75, 1.5, "Dense\nencoder", "dilated DenseBlock\nfreq. 201 → 100", fs=10.5)
    link(ax, (3.82, 2.2), (4.15, 2.2))
    node(ax, 4.15, 1.2, 2.2, 2.0, "4 × TS-Conformer", "Conformer over time\nthen over frequency", fc=MAGENTA,
         fs=10.5)
    link(ax, (6.37, 2.6), (6.9, 3.25))
    link(ax, (6.37, 1.8), (6.9, 1.15))
    node(ax, 6.9, 2.75, 2.2, 1.25, "Magnitude decoder", "mask = 2·σ(a_f·x)\n|Ŝ| = mask · |Y|", fc=CORAL,
         fs=10.5)
    node(ax, 6.9, 0.4, 2.2, 1.25, "Phase decoder", "predicts (r, i)\n∠Ŝ = atan2(i, r)", fc=AMBER, tc=INK,
         fs=10.5)
    link(ax, (9.12, 3.35), (9.5, 2.55))
    link(ax, (9.12, 1.05), (9.5, 1.85))
    node(ax, 9.5, 1.55, 1.4, 1.3, "iSTFT", "enhanced\nwaveform ŝ", fc=TINT, tc=INK, fs=10.5)
    ax.text(5.25, 0.55, "shared representation", ha="center", fontsize=9, color=MUTED, style="italic")
    save(fig, "fig_architecture.png")


def fig_tfblock():
    fig, ax = canvas(10, 2.7, (0, 10), (0, 2.7))
    node(ax, 0.1, 0.8, 1.7, 1.1, "B×C×T×F", "feature map", fc=TINT, tc=INK, fs=10)
    link(ax, (1.82, 1.35), (2.25, 1.35))
    node(ax, 2.25, 0.6, 2.6, 1.5, "Time Conformer", "each frequency bin is a\nsequence over T frames", fc=MAGENTA,
         fs=10)
    link(ax, (4.87, 1.35), (5.3, 1.35))
    node(ax, 5.3, 0.6, 2.6, 1.5, "Frequency Conformer", "each frame is a\nsequence over F bins", fc=PLUM, fs=10)
    link(ax, (7.92, 1.35), (8.3, 1.35))
    node(ax, 8.3, 0.8, 1.6, 1.1, "B×C×T×F", "same shape", fc=TINT, tc=INK, fs=10)
    ax.text(5, 2.45, "Conformer = ½FFN → multi-head self-attention → depthwise conv (k=31) → ½FFN → LayerNorm",
            ha="center", fontsize=9.5, color=MUTED)
    save(fig, "fig_tfblock.png")


def fig_phase_wrapping():
    x = np.linspace(-3 * np.pi, 3 * np.pi, 2000)
    aw = np.abs(x - np.round(x / (2 * np.pi)) * 2 * np.pi)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.0))
    axes[0].plot(x, np.abs(x), color=GREY, lw=2, label="naive |Δφ|")
    axes[0].plot(x, aw, color=CORAL, lw=2.2, label="anti-wrapping f(Δφ)")
    axes[0].set_xticks([-2 * np.pi, 0, 2 * np.pi], ["−2π", "0", "2π"])
    axes[0].set_xlabel("phase error Δφ (radians)")
    axes[0].set_ylabel("loss")
    axes[0].set_title("Phase error: 2π is not an error", loc="left")
    axes[0].legend(frameon=False, fontsize=9)
    t = np.linspace(0, 1, 400)
    true = 2 * np.pi * 6 * t
    axes[1].plot(t, np.angle(np.exp(1j * true)), color=PLUM, lw=1.6)
    axes[1].set_title("Measured phase is wrapped to (−π, π]", loc="left")
    axes[1].set_xlabel("time")
    axes[1].set_yticks([-np.pi, 0, np.pi], ["−π", "0", "π"])
    fig.tight_layout()
    save(fig, "fig_phase_wrapping.png")


def fig_compression_mask():
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.0))
    m = np.linspace(0, 1, 400)
    for c, col in [(1.0, GREY), (0.5, MAGENTA), (0.3, CORAL)]:
        axes[0].plot(m, m ** c, color=col, lw=2.2, label=f"c = {c}")
    axes[0].set_xlabel("magnitude |X|")
    axes[0].set_ylabel("|X|^c")
    axes[0].set_title("Power-law compression lifts quiet bins", loc="left")
    axes[0].legend(frameon=False, fontsize=9)
    x = np.linspace(-6, 6, 400)
    axes[1].plot(x, 1 / (1 + np.exp(-x)), color=GREY, lw=2.2, label="sigmoid (β = 1)")
    axes[1].plot(x, 2 / (1 + np.exp(-x)), color=CORAL, lw=2.2, label="learnable sigmoid (β = 2)")
    axes[1].axhline(1, color=MUTED, lw=0.8, ls="--")
    axes[1].text(-5.8, 1.05, "mask = 1 (keep the input)", fontsize=8.5, color=MUTED)
    axes[1].set_xlabel("decoder output x")
    axes[1].set_ylabel("mask value")
    axes[1].set_title("β = 2 lets the mask also amplify", loc="left")
    axes[1].legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    save(fig, "fig_compression_mask.png")


def fig_losses():
    names = ["Magnitude MSE", "Phase (IP+GD+IAF)", "Time L1", "Complex MSE", "STFT consistency", "Metric GAN"]
    w = [0.9, 0.3, 0.2, 0.1, 0.1, 0.05]
    cols = [CORAL, AMBER, PLUM, MAGENTA, PLUM, MAGENTA]
    fig, ax = plt.subplots(figsize=(8, 2.9))
    y = np.arange(len(names))[::-1]
    ax.barh(y, w, color=cols, height=0.6)
    for yi, v, n in zip(y, w, names):
        ax.text(v + 0.012, yi, f"{v:g}", va="center", fontsize=10)
    ax.set_yticks(y, names)
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("weight in the total loss")
    ax.set_title("The six training objectives and their weights", loc="left")
    ax.grid(axis="x", color="#ECE6EF")
    ax.set_axisbelow(True)
    save(fig, "fig_losses.png")


def fig_pcs():
    sys.path.insert(0, str(ROOT / "src"))
    from se.utils.pcs import pcs400_gains
    g = pcs400_gains(201).numpy()
    f = np.arange(201) * 8000 / 200 / 1000
    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.fill_between(f, 1, g, color=AMBER, alpha=0.25, step="mid")
    ax.step(f, g, where="mid", color=CORAL, lw=2.2)
    ax.set_xlabel("frequency (kHz)")
    ax.set_ylabel("gain g(f)")
    ax.set_ylim(0.95, 1.5)
    ax.set_title("PCS: stronger stretching in the bands most important for intelligibility", loc="left")
    ax.grid(color="#ECE6EF")
    save(fig, "fig_pcs.png")


def fig_pipeline():
    fig, ax = canvas(11, 2.3, (0, 11), (0, 2.3))
    steps = [("Prepare", "download VB-D\n48 → 16 kHz", PLUM), ("Configure", "base.yaml +\none change", MAGENTA),
             ("Train", "SLURM array\n7 runs", CORAL), ("Evaluate", "824 test files\n8 metrics", AMBER),
             ("Collect", "CSV · table\nchart", PLUM), ("Report", "slides & report\nauto-filled", MAGENTA)]
    for i, (h, d, c) in enumerate(steps):
        x = 0.1 + i * 1.83
        node(ax, x, 0.35, 1.5, 1.6, h, d, fc=c, tc=INK if c == AMBER else "white", fs=10.5)
        if i < len(steps) - 1:
            link(ax, (x + 1.52, 1.15), (x + 1.81, 1.15))
    save(fig, "fig_pipeline.png")


def fig_split():
    fig, ax = plt.subplots(figsize=(8, 1.7))
    parts = [("Training: 26 speakers, ≈10.8k pairs", 10800, PLUM), ("Validation: p226, p287 (≈770)", 770, AMBER),
             ("Test: 2 unseen speakers, 824", 824, CORAL)]
    left = 0
    for name, n, c in parts:
        ax.barh(0, n, left=left, color=c, height=0.55)
        left += n
    ax.text(5400, 0, parts[0][0], ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    ax.annotate(parts[1][0], (10800 + 385, 0.3), (8600, 0.75), fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.annotate(parts[2][0], (11570 + 412, -0.3), (8800, -0.8), fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.set_xlim(0, 12400)
    ax.set_ylim(-1.1, 1.1)
    ax.axis("off")
    save(fig, "fig_split.png")


# ----------------------------------------------------------------- results
def load_results(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f)) or None


def fig_results(rows):
    rr = [r for r in rows if r["run"] != "noisy" and r.get("pesq")]
    base = next((float(r["pesq"]) for r in rr if r["run"] == "a00_baseline"), None)
    labels = [f"{r['run'].split('_')[0]}  {r['description']}" for r in rr]
    vals = [float(r["pesq"]) for r in rr]
    cols = [AMBER if r["run"].startswith("a00") else GOOD if r["run"].startswith("p") else PLUM for r in rr]
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(rr) + 1.2))
    y = np.arange(len(rr))[::-1]
    ax.barh(y, vals, color=cols, height=0.62)
    for yi, v in zip(y, vals):
        ax.text(v + 0.004, yi, f"{v:.3f}", va="center", fontsize=9)
    if base:
        ax.axvline(base, color=AMBER, ls="--", lw=1.2)
    ax.set_yticks(y, labels, fontsize=9.5)
    ax.set_xlim(min(vals) - 0.15, max(vals) + 0.08)
    ax.set_xlabel("PESQ (wide-band) on the test set")
    ax.set_title("Ablation and proposals (dashed line = full baseline)", loc="left")
    ax.grid(axis="x", color="#ECE6EF")
    ax.set_axisbelow(True)
    save(fig, "fig_results.png")


def make_all(results_csv: Path, data_root: Path | None):
    fig_spectrogram(data_root)
    fig_taxonomy()
    fig_timeline()
    fig_reported_pesq()
    fig_architecture()
    fig_tfblock()
    fig_phase_wrapping()
    fig_compression_mask()
    fig_losses()
    fig_pcs()
    fig_pipeline()
    fig_split()
    rows = load_results(results_csv)
    if rows:
        fig_results(rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results" / "ablation_results.csv"))
    ap.add_argument("--data", default=str(ROOT / "data" / "voicebank_demand_16k"))
    a = ap.parse_args()
    make_all(Path(a.results), Path(a.data))
    print(f"[figures] written to {OUT}")
