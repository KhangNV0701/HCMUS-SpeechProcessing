"""Perceptual Contrast Stretching (PCS) of the training target.

PCS (Chao et al., Interspeech 2022) sharpens the *target* clean spectrum by
raising the log1p-magnitude with frequency-dependent exponents derived from
the band-importance function of the Speech Intelligibility Index. It was used
by e.g. SEMamba (IEEE SLT 2024) on top of MP-SENet-style models.

The ``PCS400`` table below follows the gains used in public PCS
implementations for a 400-point FFT (201 bins, 16 kHz). Bands most important
for intelligibility (~0.4-4.4 kHz) get the strongest stretch (1.4).
"""
from __future__ import annotations

import torch


def pcs400_gains(n_freq: int = 201) -> torch.Tensor:
    g = torch.ones(201)
    g[0:3] = 1.0
    g[3:5] = 1.070175439
    g[5:8] = 1.182456140
    g[8:10] = 1.287719298
    g[10:110] = 1.4
    g[110:130] = 1.287719298
    g[130:160] = 1.182456140
    g[160:190] = 1.070175439
    g[190:] = 1.0
    if n_freq != 201:
        # Linearly re-sample the gain curve to another FFT size.
        g = torch.nn.functional.interpolate(g.view(1, 1, -1), size=n_freq, mode="linear",
                                            align_corners=True).view(-1)
    return g


@torch.no_grad()
def apply_pcs(wav: torch.Tensor, n_fft: int = 400, hop_length: int = 100,
              win_length: int = 400) -> torch.Tensor:
    """Apply PCS to a waveform ``(L,)`` or ``(B, L)``; returns same shape."""
    squeeze = wav.dim() == 1
    if squeeze:
        wav = wav.unsqueeze(0)
    window = torch.hann_window(win_length, device=wav.device)
    spec = torch.stft(wav, n_fft, hop_length, win_length, window=window, center=True,
                      return_complex=True)
    mag, pha = spec.abs(), spec.angle()
    gains = pcs400_gains(n_fft // 2 + 1).to(wav.device).view(1, -1, 1)
    mag = torch.expm1(gains * torch.log1p(mag))
    out = torch.istft(torch.polar(mag, pha), n_fft, hop_length, win_length, window=window,
                      center=True, length=wav.shape[-1])
    return out.squeeze(0) if squeeze else out
