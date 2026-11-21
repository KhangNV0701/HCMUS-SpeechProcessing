"""Create a tiny synthetic paired dataset (harmonic 'speech-like' tones + noise) for smoke tests.

    python scripts/make_dummy_data.py --out data/dummy
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf


def synth_utterance(rng, sr, seconds):
    t = np.arange(int(sr * seconds)) / sr
    f0 = 100 + 80 * rng.random() + 20 * np.sin(2 * np.pi * rng.uniform(0.5, 2) * t)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    sig = sum((0.6 / k) * np.sin(k * phase) for k in range(1, 12))
    env = (np.sin(2 * np.pi * rng.uniform(2, 4) * t) > -0.2).astype(float)
    env = np.convolve(env, np.ones(400) / 400, mode="same")
    return (0.1 * sig * env).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/dummy")
    ap.add_argument("--n_train", type=int, default=8)
    ap.add_argument("--n_test", type=int, default=3)
    ap.add_argument("--sr", type=int, default=16000)
    args = ap.parse_args()
    rng = np.random.default_rng(0)
    root = Path(args.out)
    for split, n, prefix in [("trainset_28spk", args.n_train, "p001"), ("testset", args.n_test, "p232")]:
        cdir, ndir = root / f"clean_{split}_wav", root / f"noisy_{split}_wav"
        cdir.mkdir(parents=True, exist_ok=True)
        ndir.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            clean = synth_utterance(rng, args.sr, rng.uniform(1.5, 3.0))
            snr = rng.choice([2.5, 7.5, 12.5, 17.5])
            noise = rng.standard_normal(len(clean)).astype(np.float32)
            noise *= np.sqrt(np.mean(clean ** 2) / (np.mean(noise ** 2) * 10 ** (snr / 10)))
            name = f"{prefix}_{i:03d}.wav"
            sf.write(cdir / name, clean, args.sr)
            sf.write(ndir / name, clean + noise, args.sr)
    print(f"[done] dummy data in {root}")


if __name__ == "__main__":
    main()
