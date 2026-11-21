"""Enhance arbitrary wav files (a file or a directory) with a trained checkpoint.

    python -m se.enhance --ckpt runs/a00_baseline/checkpoints/best.pt --input noisy.wav --output out/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

from .inference import enhance, load_model


def read_any(path: Path, sr: int) -> np.ndarray:
    wav, file_sr = sf.read(str(path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if file_sr != sr:
        g = np.gcd(file_sr, sr)
        wav = resample_poly(wav, sr // g, file_sr // g).astype(np.float32)
    return wav


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--input", required=True, help="wav file or directory of wavs")
    ap.add_argument("--output", required=True, help="output directory")
    ap.add_argument("--chunk_seconds", type=float, default=None,
                    help="process long files in chunks (e.g. 10) to limit memory")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args(argv)

    model, stft, cfg = load_model(args.ckpt, args.device)
    sr = cfg.data.sample_rate
    inp, out = Path(args.input), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(inp.glob("*.wav")) if inp.is_dir() else [inp]
    for f in files:
        wav = read_any(f, sr)
        est = enhance(model, stft, torch.from_numpy(wav), sr, args.chunk_seconds).numpy()
        sf.write(out / f.name, est, sr)
        print(f"[se] {f.name} -> {out / f.name}")


if __name__ == "__main__":
    main()
