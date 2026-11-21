import itertools

import pytest
import torch

from se.losses import GeneratorLoss, MultiResolutionSTFTLoss, anti_wrapping
from se.models import Generator, MetricDiscriminator
from se.utils import STFT
from se.utils.config import apply_overrides, deep_merge
from se.utils.pcs import apply_pcs


@pytest.fixture(scope="module")
def stft():
    return STFT(400, 100, 400, 0.3)


def test_stft_roundtrip(stft):
    x = torch.randn(2, 16000)
    mag, pha, com = stft.analysis(x)
    assert mag.shape == (2, 201, 161) and com.shape == (2, 201, 161, 2)
    y = stft.synthesis(mag, pha, length=16000)
    assert torch.allclose(x, y, atol=1e-3)


@pytest.mark.parametrize("decoder,tf_block,mask", list(itertools.product(
    ["parallel", "mag_only", "complex"], ["conformer", "lstm", "none"], ["lsigmoid"])) +
    [("parallel", "conformer", "sigmoid"), ("parallel", "conformer", "relu")])
def test_generator_variants(stft, decoder, tf_block, mask):
    g = Generator(n_freq=201, dense_channel=16, num_tf_blocks=1, tf_block=tf_block, decoder=decoder,
                  mask_activation=mask, conformer={"heads": 4, "dropout": 0.0})
    x = torch.randn(2, 8000)
    mag, pha, _ = stft.analysis(x)
    m, p, c = g(mag, pha)
    assert m.shape == mag.shape and p.shape == pha.shape and c.shape == (*mag.shape, 2)
    m.mean().backward()


def test_full_size_param_count():
    g = Generator()  # paper configuration
    n = sum(p.numel() for p in g.parameters())
    assert 1.5e6 < n < 2.6e6, n  # MP-SENet reports ~2.05 M parameters


def test_discriminator_and_losses(stft):
    d = MetricDiscriminator()
    x = torch.randn(2, 16000)
    mag, pha, com = stft.analysis(x)
    out = d(mag, mag)
    assert out.shape == (2, 1) and (out > 0).all() and (out < 1).all()
    crit = GeneratorLoss({"magnitude": 0.9, "phase": 0.3, "complex": 0.1, "time": 0.2,
                          "consistency": 0.1, "metric": 0.05, "mrstft": 0.1})
    total, terms = crit(clean_mag=mag, clean_pha=pha, clean_com=com, clean_wav=x, mag_g=mag,
                        pha_g=pha, com_g=com, wav_g=x, com_g_hat=com, metric_g=out)
    assert torch.isfinite(total) and terms["magnitude"] == 0.0 and "mrstft" in terms


def test_anti_wrapping():
    x = torch.tensor([0.0, 2 * torch.pi, -2 * torch.pi + 0.1])
    assert torch.allclose(anti_wrapping(x), torch.tensor([0.0, 0.0, 0.1]), atol=1e-6)


def test_mrstft_zero_for_identical():
    x = torch.randn(1, 16000)
    assert MultiResolutionSTFTLoss()(x, x).item() < 1e-5


def test_pcs_shape_and_effect():
    x = 0.1 * torch.randn(16000)
    y = apply_pcs(x)
    assert y.shape == x.shape and not torch.allclose(x, y)


def test_config_merge_and_override():
    cfg = deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}})
    assert cfg == {"a": {"b": 3, "c": 2}}
    cfg = apply_overrides(cfg, ["a.c=5", "d.e=[1, 2]"])
    assert cfg["a"]["c"] == 5 and cfg["d"]["e"] == [1, 2]
