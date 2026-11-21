"""Metric suite: PESQ(wb), CSIG, CBAK, COVL, SSNR, STOI, SI-SDR."""
from __future__ import annotations

import numpy as np

from .composite import composite, seg_snr  # noqa: F401


def si_sdr(ref: np.ndarray, est: np.ndarray, eps: float = 1e-8) -> float:
    ref = ref - ref.mean()
    est = est - est.mean()
    alpha = np.dot(est, ref) / (np.dot(ref, ref) + eps)
    target = alpha * ref
    noise = est - target
    return float(10 * np.log10((np.sum(target ** 2) + eps) / (np.sum(noise ** 2) + eps)))


def pesq_wb(ref: np.ndarray, est: np.ndarray, sr: int = 16000) -> float:
    try:
        from pesq import pesq
    except ImportError as exc:  # pragma: no cover
        raise ImportError("`pip install pesq` is required for evaluation") from exc
    return float(pesq(sr, ref, est, "wb"))


def stoi(ref: np.ndarray, est: np.ndarray, sr: int = 16000, extended: bool = False) -> float:
    from pystoi import stoi as _stoi

    return float(_stoi(ref, est, sr, extended=extended))


def all_metrics(ref: np.ndarray, est: np.ndarray, sr: int = 16000, use_pesq: bool = True) -> dict:
    """Compute the full metric suite for one utterance (1-D float arrays, same length)."""
    n = min(len(ref), len(est))
    ref, est = ref[:n].astype(np.float64), est[:n].astype(np.float64)
    out = {}
    p = pesq_wb(ref, est, sr) if use_pesq else float("nan")
    out["pesq"] = p
    comp = composite(ref, est, sr, p if use_pesq else 1.0)
    if not use_pesq:
        comp.update(csig=float("nan"), cbak=float("nan"), covl=float("nan"))
    out.update(comp)
    out["stoi"] = stoi(ref, est, sr)
    out["estoi"] = stoi(ref, est, sr, extended=True)
    out["si_sdr"] = si_sdr(ref, est)
    return out


METRIC_KEYS = ["pesq", "csig", "cbak", "covl", "ssnr", "stoi", "estoi", "si_sdr"]
