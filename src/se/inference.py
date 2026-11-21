"""Inference helpers shared by evaluate / enhance / demo app."""
from __future__ import annotations

from pathlib import Path

import torch

from .models import build_generator
from .utils import STFT, Config


def load_model(ckpt_path: str | Path, device: str | torch.device = "cpu"):
    ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    cfg = Config.wrap(ckpt["config"])
    stft = STFT.from_config(cfg.stft)
    model = build_generator(cfg, stft.n_freq)
    model.load_state_dict(ckpt["generator"])
    model.to(device).eval()
    return model, stft, cfg


@torch.no_grad()
def _enhance_segment(model, stft: STFT, noisy: torch.Tensor) -> torch.Tensor:
    """noisy (B, L) on the model's device -> enhanced (B, L)."""
    factor = torch.sqrt(noisy.shape[-1] / (noisy.pow(2).sum(-1, keepdim=True) + 1e-8))
    mag, pha, _ = stft.analysis(noisy * factor)
    mag_g, pha_g, _ = model(mag, pha)
    out = stft.synthesis(mag_g, pha_g, length=noisy.shape[-1])
    return out / factor


@torch.no_grad()
def enhance(model, stft: STFT, noisy: torch.Tensor, sr: int = 16000,
            chunk_seconds: float | None = None, overlap_seconds: float = 0.5) -> torch.Tensor:
    """Enhance a 1-D waveform. Long inputs can be processed in overlapping chunks
    (linear cross-fade) to bound memory; ``chunk_seconds=None`` processes it whole."""
    device = next(model.parameters()).device
    x = noisy.to(device).float().view(1, -1)
    n = x.shape[-1]
    if not chunk_seconds or n <= int(chunk_seconds * sr):
        return _enhance_segment(model, stft, x).view(-1).cpu()
    chunk, ov = int(chunk_seconds * sr), int(overlap_seconds * sr)
    hop = chunk - ov
    out = torch.zeros(n, device=device)
    weight = torch.zeros(n, device=device)
    fade = torch.ones(chunk, device=device)
    if ov > 0:
        ramp = torch.linspace(0, 1, ov, device=device)
        fade[:ov], fade[-ov:] = ramp, ramp.flip(0)
    start = 0
    while start < n:
        end = min(start + chunk, n)
        seg = x[:, start:end]
        if seg.shape[-1] < chunk:  # last chunk: pad to keep normalisation stable
            seg = torch.nn.functional.pad(seg, (0, chunk - seg.shape[-1]))
        y = _enhance_segment(model, stft, seg).view(-1)[: end - start]
        length = end - start
        w = fade[:length].clone()
        if start == 0 and ov > 0:
            w[:ov] = 1.0  # no fade-in at the very beginning
        if end == n:  # no fade-out at the very end
            w[-min(ov, length):] = 1.0
        out[start:end] += y * w
        weight[start:end] += w
        if end == n:
            break
        start += hop
    return (out / weight.clamp_min(1e-6)).cpu()
