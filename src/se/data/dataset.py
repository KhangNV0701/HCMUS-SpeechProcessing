"""Paired clean / noisy dataset (VoiceBank-DEMAND layout: same file names in both dirs)."""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch.utils.data import Dataset

from ..utils.pcs import apply_pcs


def list_pairs(clean_dir: str | Path, noisy_dir: str | Path, speakers_in=None, speakers_out=None):
    clean_dir, noisy_dir = Path(clean_dir), Path(noisy_dir)
    names = sorted(p.name for p in clean_dir.glob("*.wav"))
    if speakers_in:
        names = [n for n in names if n.split("_")[0] in set(speakers_in)]
    if speakers_out:
        names = [n for n in names if n.split("_")[0] not in set(speakers_out)]
    pairs = [(clean_dir / n, noisy_dir / n) for n in names if (noisy_dir / n).exists()]
    if not pairs:
        raise FileNotFoundError(f"No paired wavs found in {clean_dir} / {noisy_dir}")
    return pairs


def load_wav(path: Path, sr: int) -> np.ndarray:
    wav, file_sr = sf.read(str(path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if file_sr != sr:
        raise ValueError(f"{path}: expected {sr} Hz, got {file_sr} Hz (run scripts/prepare_vbd.py)")
    return wav


class PairedDataset(Dataset):
    """Returns (clean, noisy, name). In training mode, random fixed-length segments."""

    def __init__(self, pairs, sample_rate: int = 16000, segment_seconds: float | None = 2.0,
                 train: bool = True, pcs: bool = False, stft_cfg=None):
        self.pairs = list(pairs)
        self.sr = sample_rate
        self.segment = int(segment_seconds * sample_rate) if segment_seconds else None
        self.train = train
        self.pcs = pcs
        self.stft_cfg = stft_cfg

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int):
        clean_p, noisy_p = self.pairs[idx]
        clean = torch.from_numpy(load_wav(clean_p, self.sr))
        noisy = torch.from_numpy(load_wav(noisy_p, self.sr))
        n = min(len(clean), len(noisy))
        clean, noisy = clean[:n], noisy[:n]
        if self.train and self.segment:
            if n >= self.segment:
                start = random.randint(0, n - self.segment)
                clean, noisy = clean[start:start + self.segment], noisy[start:start + self.segment]
            else:
                pad = self.segment - n
                clean = torch.nn.functional.pad(clean, (0, pad))
                noisy = torch.nn.functional.pad(noisy, (0, pad))
        if self.pcs and self.train:
            s = self.stft_cfg
            clean = apply_pcs(clean, s.n_fft, s.hop_length, s.win_length)
        return clean, noisy, clean_p.stem
