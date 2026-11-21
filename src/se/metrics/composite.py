"""Objective quality measures used on VoiceBank-DEMAND.

CSIG / CBAK / COVL follow Hu & Loizou, "Evaluation of objective quality
measures for speech enhancement", IEEE TASLP 2008, combining LLR, WSS,
segmental SNR and PESQ. The frame-level measures mirror the widely used
Python port (``compute_metrics.py`` in MetricGAN/CMGAN/MP-SENet repos):
30 ms Hann frames, 75 % overlap, 95 % of the lowest LLR / WSS frames kept.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.linalg import toeplitz

EPS = np.finfo(np.float64).eps


def _frames(x: np.ndarray, win: int, hop: int) -> np.ndarray:
    n = int(len(x) / hop - (win / hop))
    if n <= 0:
        return np.zeros((0, win))
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    window = 0.5 * (1 - np.cos(2 * math.pi * np.arange(1, win + 1) / (win + 1)))
    return x[idx] * window[None, :]


def _framing_params(sr: int):
    win = int(round(30 * sr / 1000))
    return win, int(np.floor(win / 4))


# ---------------------------------------------------------------- segSNR
def seg_snr(clean: np.ndarray, est: np.ndarray, sr: int, lo: float = -10, hi: float = 35) -> float:
    win, hop = _framing_params(sr)
    c, e = _frames(clean, win, hop), _frames(est, win, hop)
    sig = np.sum(c ** 2, axis=1)
    noise = np.sum((c - e) ** 2, axis=1)
    seg = 10 * np.log10(sig / (noise + EPS) + EPS)
    return float(np.mean(np.clip(seg, lo, hi)))


# ------------------------------------------------------------------- LLR
def _lpc(frame: np.ndarray, order: int):
    win = len(frame)
    r = np.array([np.dot(frame[: win - k], frame[k:]) for k in range(order + 1)])
    a = np.zeros(order)
    err = r[0] + EPS
    for i in range(order):
        acc = r[i + 1] - np.dot(a[:i], r[i:0:-1]) if i > 0 else r[1]
        k = acc / err
        a_prev = a[:i].copy()
        a[i] = k
        if i > 0:
            a[:i] = a_prev - k * a_prev[::-1]
        err = (1 - k * k) * err + EPS
    return r, np.concatenate(([1.0], -a))


def llr(clean: np.ndarray, est: np.ndarray, sr: int) -> np.ndarray:
    win, hop = _framing_params(sr)
    order = 10 if sr < 10000 else 16
    c, e = _frames(clean, win, hop), _frames(est, win, hop)
    out = np.empty(len(c))
    for n in range(len(c)):
        r_c, a_c = _lpc(c[n], order)
        _, a_e = _lpc(e[n], order)
        t = toeplitz(r_c)
        num = a_e @ t @ a_e
        den = a_c @ t @ a_c
        out[n] = np.log(max(num, EPS) / max(den, EPS))
    return out


# ------------------------------------------------------------------- WSS
_CENT = [50.0, 120.0, 190.0, 260.0, 330.0, 400.0, 470.0, 540.0, 617.372, 703.378, 798.717, 904.128,
         1020.38, 1148.30, 1288.72, 1442.54, 1610.70, 1794.16, 1993.93, 2210.08, 2443.67, 2695.83,
         2966.69, 3257.35, 3568.85]
_BW = [70.0, 70.0, 70.0, 70.0, 70.0, 70.0, 70.0, 77.3724, 86.0056, 95.3398, 105.411, 116.256, 127.914,
       140.423, 153.823, 168.154, 183.457, 199.776, 217.153, 235.631, 255.255, 276.072, 298.126,
       321.465, 346.136]


def wss(clean: np.ndarray, est: np.ndarray, sr: int, kmax: float = 20.0, klocmax: float = 1.0) -> np.ndarray:
    win, hop = _framing_params(sr)
    n_fft = int(2 ** np.ceil(np.log2(2 * win)))
    half = n_fft // 2
    max_freq = sr / 2
    num_crit = len(_CENT)
    min_factor = math.exp(-30.0 / (2.0 * 2.303))
    j = np.arange(half)
    filt = np.empty((num_crit, half))
    for i in range(num_crit):
        f0 = _CENT[i] / max_freq * half
        bw = _BW[i] / max_freq * half
        norm = np.log(_BW[0]) - np.log(_BW[i])
        filt[i] = np.exp(-11 * ((j - np.floor(f0)) / bw) ** 2 + norm)
        filt[i][filt[i] <= min_factor] = 0.0

    def band_db(frames):
        spec = np.abs(np.fft.fft(frames / 32768.0, n_fft, axis=1)[:, :half]) ** 2
        energy = spec @ filt.T
        return 10 * np.log10(np.maximum(energy, 1e-10))

    def loc_peaks(energy, slope):
        peaks = np.empty((energy.shape[0], num_crit - 1))
        for f in range(energy.shape[0]):
            for i in range(num_crit - 1):
                n = i
                if slope[f, i] > 0:
                    while n < num_crit - 1 and slope[f, n] > 0:
                        n += 1
                    peaks[f, i] = energy[f, n - 1]
                else:
                    while n >= 0 and slope[f, n] <= 0:
                        n -= 1
                    peaks[f, i] = energy[f, n + 1]
        return peaks

    ec, ee = band_db(_frames(clean, win, hop)), band_db(_frames(est, win, hop))
    sc, se = np.diff(ec, axis=1), np.diff(ee, axis=1)
    pc, pe = loc_peaks(ec, sc), loc_peaks(ee, se)
    wc = (kmax / (kmax + ec.max(1, keepdims=True) - ec[:, :-1])) * (klocmax / (klocmax + pc - ec[:, :-1]))
    we = (kmax / (kmax + ee.max(1, keepdims=True) - ee[:, :-1])) * (klocmax / (klocmax + pe - ee[:, :-1]))
    w = (wc + we) / 2.0
    return np.sum(w * (sc - se) ** 2, axis=1) / np.sum(w, axis=1)


def _trimmed_mean(x: np.ndarray, alpha: float = 0.95) -> float:
    x = np.sort(x)
    return float(np.mean(x[: int(round(len(x) * alpha))]))


def composite(clean: np.ndarray, est: np.ndarray, sr: int, pesq_wb: float) -> dict:
    llr_m = _trimmed_mean(llr(clean, est, sr))
    wss_m = _trimmed_mean(wss(clean, est, sr))
    ssnr = seg_snr(clean, est, sr)
    csig = 3.093 - 1.029 * llr_m + 0.603 * pesq_wb - 0.009 * wss_m
    cbak = 1.634 + 0.478 * pesq_wb - 0.007 * wss_m + 0.063 * ssnr
    covl = 1.594 + 0.805 * pesq_wb - 0.512 * llr_m - 0.007 * wss_m
    clip = lambda v: float(min(max(v, 1.0), 5.0))  # noqa: E731
    return {"csig": clip(csig), "cbak": clip(cbak), "covl": clip(covl), "ssnr": ssnr,
            "llr": llr_m, "wss": wss_m}
