"""Aggregate ``runs/*/eval/summary.json`` into an ablation table (CSV + Markdown + plot).

    python scripts/collect_results.py --runs runs --out results

Rows are ordered as in configs/experiments.txt; deltas are w.r.t. a00_baseline.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

KEYS = ["pesq", "csig", "cbak", "covl", "ssnr", "stoi", "si_sdr", "n_params_M", "rtf"]
DESCRIPTIONS = {
    "noisy": "Noisy input (no processing)",
    "a00_baseline": "Full baseline (MP-SENet-style)",
    "a01_no_metric_disc": "no metric discriminator",
    "a02_no_phase_loss": "no phase losses",
    "a03_no_consistency": "no consistency loss",
    "a04_no_time_complex": "no time + complex losses",
    "a05_mag_only": "magnitude-only decoder (noisy phase)",
    "a06_complex_mapping": "complex-mapping decoder",
    "a07_no_compression": "no magnitude compression (c = 1)",
    "a08_two_tf_blocks": "2 TS-Conformer blocks",
    "a09_lstm_tf_blocks": "BiLSTM instead of Conformer",
    "a10_sigmoid_mask": "plain sigmoid mask (beta = 1)",
    "p01_mrstft": "+ MR-STFT loss (proposed)",
    "p02_pcs": "+ PCS target (proposed)",
    "p03_mrstft_pcs": "+ MR-STFT + PCS (proposed)",
}


def describe(cfg_path: Path) -> tuple[str, str]:
    text = cfg_path.read_text(encoding="utf-8")
    first = text.splitlines()[0].lstrip("# ").strip() if text.startswith("#") else ""
    name = yaml.safe_load(text).get("experiment", {}).get("name", cfg_path.stem)
    return name, first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--out", default="results")
    ap.add_argument("--experiments", default="configs/experiments.txt")
    args = ap.parse_args()

    runs, out = Path(args.runs), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    order = [("noisy", DESCRIPTIONS["noisy"])]
    for line in Path(args.experiments).read_text().split():
        name, desc = describe(Path(line))
        order.append((name, DESCRIPTIONS.get(name, desc)))

    rows = []
    for name, desc in order:
        f = runs / name / "eval" / "summary.json"
        if not f.exists():
            print(f"[missing] {f}")
            continue
        s = json.loads(f.read_text())
        rows.append({"run": name, "description": desc, **{k: s.get(k) for k in KEYS}})
    if not rows:
        print("no results found")
        return

    base = next((r for r in rows if r["run"] == "a00_baseline"), None)
    with open(out / "ablation_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["run", "description"] + KEYS + ["delta_pesq"])
        w.writeheader()
        for r in rows:
            d = dict(r)
            if base and r["pesq"] is not None:
                d["delta_pesq"] = r["pesq"] - base["pesq"]
            w.writerow(d)

    fmt = lambda v, n=2: "-" if v is None else f"{v:.{n}f}"  # noqa: E731
    lines = ["| Run | Description | PESQ | ΔPESQ | CSIG | CBAK | COVL | SSNR | STOI | SI-SDR | Params (M) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        dp = fmt(r["pesq"] - base["pesq"], 3) if base and r["run"] != "noisy" else "-"
        lines.append(f"| {r['run']} | {r['description']} | {fmt(r['pesq'], 3)} | {dp} | {fmt(r['csig'])} | "
                     f"{fmt(r['cbak'])} | {fmt(r['covl'])} | {fmt(r['ssnr'])} | {fmt(r['stoi'], 3)} | "
                     f"{fmt(r['si_sdr'])} | {fmt(r['n_params_M'])} |")
    (out / "ablation_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        sys.stdout.reconfigure(errors="replace")  # Windows consoles cannot print "Δ"
    except AttributeError:
        pass
    print("\n".join(lines))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        rr = [r for r in rows if r["run"] != "noisy" and r["pesq"] is not None]
        fig, ax = plt.subplots(figsize=(10, 4.5))
        colors = ["#2563eb" if r["run"].startswith("a00") else "#16a34a" if r["run"].startswith("p")
                  else "#94a3b8" for r in rr]
        ax.bar([r["run"] for r in rr], [r["pesq"] for r in rr], color=colors)
        if base:
            ax.axhline(base["pesq"], color="#2563eb", lw=1, ls="--")
        lo = min(r["pesq"] for r in rr)
        ax.set_ylim(max(1.0, lo - 0.15), max(r["pesq"] for r in rr) + 0.08)
        ax.set_ylabel("PESQ (wb)")
        ax.set_title("Ablation on VoiceBank-DEMAND test set")
        plt.xticks(rotation=40, ha="right")
        plt.tight_layout()
        fig.savefig(out / "ablation_pesq.png", dpi=200)
        print(f"[saved] {out / 'ablation_pesq.png'}")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
