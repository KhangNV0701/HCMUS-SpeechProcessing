"""Training objectives.

Generator objective (weights from ``loss.*`` in the config, paper defaults):
    0.9 * magnitude MSE  + 0.3 * anti-wrapping phase loss (IP + GD + IAF)
  + 0.1 * complex MSE    + 0.2 * time-domain L1
  + 0.1 * STFT consistency + 0.05 * metric (GAN) loss
  + (proposed) mrstft * multi-resolution STFT loss
Setting a weight to 0 removes that term (used by the ablation configs).
"""
from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn.functional as F


# ------------------------------------------------------------------- phase
def anti_wrapping(x: torch.Tensor) -> torch.Tensor:
    return torch.abs(x - torch.round(x / (2 * math.pi)) * 2 * math.pi)


def phase_losses(pha_ref: torch.Tensor, pha_est: torch.Tensor):
    """Instantaneous phase, group delay (freq. diff) and inst. angular freq. (time diff)."""
    ip = anti_wrapping(pha_ref - pha_est).mean()
    gd = anti_wrapping(torch.diff(pha_ref, dim=1) - torch.diff(pha_est, dim=1)).mean()
    iaf = anti_wrapping(torch.diff(pha_ref, dim=2) - torch.diff(pha_est, dim=2)).mean()
    return ip, gd, iaf


# --------------------------------------------------------------- MR-STFT
class MultiResolutionSTFTLoss(torch.nn.Module):
    """Spectral convergence + log-magnitude L1 at several resolutions (Yamamoto et al.)."""

    def __init__(self, resolutions=((512, 128, 512), (1024, 256, 1024), (256, 64, 256))):
        super().__init__()
        self.resolutions = [tuple(r) for r in resolutions]

    def forward(self, est: torch.Tensor, ref: torch.Tensor) -> torch.Tensor:
        total = 0.0
        for n_fft, hop, win in self.resolutions:
            window = torch.hann_window(win, device=est.device)
            e = torch.stft(est, n_fft, hop, win, window, return_complex=True).abs().clamp_min(1e-7)
            r = torch.stft(ref, n_fft, hop, win, window, return_complex=True).abs().clamp_min(1e-7)
            sc = torch.norm(r - e, p="fro") / torch.norm(r, p="fro").clamp_min(1e-7)
            mag = F.l1_loss(torch.log(e), torch.log(r))
            total = total + sc + mag
        return total / len(self.resolutions)


# --------------------------------------------------------------- PESQ (D)
def _pesq_one(ref: np.ndarray, est: np.ndarray, sr: int) -> float:
    from pesq import pesq  # imported lazily: optional on machines without a C compiler

    try:
        return pesq(sr, ref, est, "wb")
    except Exception:  # NoUtterancesError, too-short input, ...
        return -1.0


def batch_pesq_normalized(ref: torch.Tensor, est: torch.Tensor, sr: int = 16000):
    """Wide-band PESQ of each item, normalised to [0, 1] as (pesq - 1) / 3.5.

    Returns ``None`` if any item fails (the discriminator step then skips the fake term,
    as in the reference implementation).
    """
    ref_np = ref.detach().float().cpu().numpy()
    est_np = est.detach().float().cpu().numpy()
    scores = [_pesq_one(r, e, sr) for r, e in zip(ref_np, est_np)]
    if any(s < 0 for s in scores):
        return None
    return torch.tensor([(s - 1.0) / 3.5 for s in scores], dtype=torch.float32).view(-1, 1)


class GeneratorLoss(torch.nn.Module):
    def __init__(self, weights):
        super().__init__()
        self.w = dict(weights)
        self.mrstft = MultiResolutionSTFTLoss() if self.w.get("mrstft", 0) > 0 else None

    def forward(self, *, clean_mag, clean_pha, clean_com, clean_wav,
                mag_g, pha_g, com_g, wav_g, com_g_hat, metric_g=None):
        w = self.w
        terms = {}
        terms["magnitude"] = F.mse_loss(clean_mag, mag_g)
        ip, gd, iaf = phase_losses(clean_pha, pha_g)
        terms["phase"] = ip + gd + iaf
        terms["complex"] = F.mse_loss(clean_com, com_g) * 2
        terms["time"] = F.l1_loss(clean_wav, wav_g)
        terms["consistency"] = F.mse_loss(com_g, com_g_hat) * 2
        if metric_g is not None:
            terms["metric"] = F.mse_loss(metric_g, torch.ones_like(metric_g))
        if self.mrstft is not None:
            terms["mrstft"] = self.mrstft(wav_g, clean_wav)
        total = sum(w.get(k, 0.0) * v for k, v in terms.items())
        return total, {k: float(v.detach()) for k, v in terms.items()}
