"""Evaluate a checkpoint on the VoiceBank-DEMAND test set (824 utterances).

    python -m se.evaluate --ckpt runs/a00_baseline/checkpoints/best.pt
    python -m se.evaluate --noisy_baseline --config configs/base.yaml   # metrics of the unprocessed input

Writes ``<out>/per_file.csv`` and ``<out>/summary.json`` (mean of every metric,
plus parameter count and real-time factor).
"""
from __future__ import annotations

import argparse
import csv
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from tqdm import tqdm

from .data import build_splits, load_wav
from .inference import enhance, load_model
from .metrics import METRIC_KEYS, all_metrics
from .utils import load_config
from .utils.misc import count_parameters, write_json


def _metrics_job(args):
    name, ref, est, sr = args
    m = all_metrics(ref, est, sr)
    m["name"] = name
    return m


def _summarise(rows, out_dir: Path, extra: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "per_file.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name"] + METRIC_KEYS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    summary = {k: float(np.nanmean([r[k] for r in rows])) for k in METRIC_KEYS}
    summary.update(extra)
    summary["n_files"] = len(rows)
    write_json(summary, out_dir / "summary.json")
    print("[se] " + "  ".join(f"{k}={summary[k]:.3f}" for k in METRIC_KEYS))
    return summary


def evaluate_checkpoint(ckpt, out_dir, device=None, num_workers: int = 8, save_wavs: bool = False,
                        chunk_seconds=None, data_root=None):
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model, stft, cfg = load_model(ckpt, device)
    if data_root:
        cfg.data.root = data_root
    sr = cfg.data.sample_rate
    _, _, test_pairs = build_splits(cfg)
    out_dir = Path(out_dir)
    wav_dir = out_dir / "wavs"
    if save_wavs:
        wav_dir.mkdir(parents=True, exist_ok=True)

    jobs, total_audio, total_time = [], 0.0, 0.0
    for clean_p, noisy_p in tqdm(test_pairs, desc="enhance"):
        clean, noisy = load_wav(clean_p, sr), load_wav(noisy_p, sr)
        if str(device).startswith("cuda"):
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        est = enhance(model, stft, torch.from_numpy(noisy), sr, chunk_seconds).numpy()
        if str(device).startswith("cuda"):
            torch.cuda.synchronize()
        total_time += time.perf_counter() - t0
        total_audio += len(noisy) / sr
        if save_wavs:
            sf.write(wav_dir / clean_p.name, est, sr)
        jobs.append((clean_p.stem, clean, est, sr))

    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        rows = list(tqdm(ex.map(_metrics_job, jobs, chunksize=8), total=len(jobs), desc="metrics"))
    extra = {"checkpoint": str(ckpt), "n_params_M": count_parameters(model) / 1e6,
             "rtf": total_time / max(total_audio, 1e-9), "device": str(device)}
    return _summarise(rows, out_dir, extra)


def evaluate_noisy(cfg, out_dir, num_workers: int = 8):
    sr = cfg.data.sample_rate
    _, _, test_pairs = build_splits(cfg)
    jobs = [(c.stem, load_wav(c, sr), load_wav(n, sr), sr) for c, n in test_pairs]
    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        rows = list(tqdm(ex.map(_metrics_job, jobs, chunksize=8), total=len(jobs), desc="metrics"))
    return _summarise(rows, Path(out_dir), {"checkpoint": "noisy (unprocessed)", "n_params_M": 0.0})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt")
    ap.add_argument("--out", default=None, help="default: <run>/eval")
    ap.add_argument("--data_root", default=None, help="override data.root stored in the checkpoint")
    ap.add_argument("--num_workers", type=int, default=8)
    ap.add_argument("--save_wavs", action="store_true")
    ap.add_argument("--chunk_seconds", type=float, default=None)
    ap.add_argument("--noisy_baseline", action="store_true")
    ap.add_argument("--config", default="configs/base.yaml")
    args = ap.parse_args(argv)

    if args.noisy_baseline:
        cfg = load_config(args.config)
        evaluate_noisy(cfg, args.out or "runs/noisy/eval", args.num_workers)
        return
    if not args.ckpt:
        ap.error("--ckpt is required (or use --noisy_baseline)")
    out = args.out or Path(args.ckpt).parent.parent / "eval"
    evaluate_checkpoint(args.ckpt, out, num_workers=args.num_workers, save_wavs=args.save_wavs,
                        chunk_seconds=args.chunk_seconds, data_root=args.data_root)


if __name__ == "__main__":
    main()
