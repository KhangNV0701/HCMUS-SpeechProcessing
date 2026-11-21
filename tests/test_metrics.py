import numpy as np
import pytest

from se.metrics import composite, seg_snr, si_sdr, stoi
from se.metrics.composite import llr, wss


def _speechlike(sr=16000, seconds=2.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(sr * seconds)) / sr
    x = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate([150, 300, 450, 900, 1800], 1))
    return (0.1 * x * (1 + 0.5 * np.sin(2 * np.pi * 3 * t)) + 0.001 * rng.standard_normal(len(t)))


def test_identical_signals_are_perfect():
    x = _speechlike()
    assert si_sdr(x, x) > 60
    assert seg_snr(x, x, 16000) == pytest.approx(35.0)
    assert np.allclose(llr(x, x, 16000), 0.0, atol=1e-6)
    assert np.allclose(wss(x, x, 16000), 0.0, atol=1e-6)
    assert stoi(x, x) > 0.99


def test_noise_degrades_metrics():
    x = _speechlike()
    y = x + 0.05 * np.random.default_rng(1).standard_normal(len(x))
    assert si_sdr(x, y) < si_sdr(x, x)
    clean_c = composite(x, x, 16000, pesq_wb=4.5)
    noisy_c = composite(x, y, 16000, pesq_wb=1.5)
    for k in ("csig", "cbak", "covl"):
        assert noisy_c[k] < clean_c[k]
        assert 1.0 <= noisy_c[k] <= 5.0


def test_pesq_if_available():
    pesq = pytest.importorskip("pesq")
    x = _speechlike()
    assert pesq.pesq(16000, x, x, "wb") > 4.0
