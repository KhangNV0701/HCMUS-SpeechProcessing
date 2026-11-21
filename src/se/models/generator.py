"""MP-SENet-style generator with switches for ablation studies.

Reference: Y.-X. Lu, Y. Ai, Z.-H. Ling, "MP-SENet: A Speech Enhancement Model
with Parallel Denoising of Magnitude and Phase Spectra", Interspeech 2023.
This is an independent re-implementation; see ``configs/`` for the switches.

Ablation switches (``model.*`` in the config):
    tf_block         conformer | lstm | none
    num_tf_blocks    int (paper: 4)
    decoder          parallel  : magnitude-mask decoder + explicit phase decoder (paper)
                     mag_only  : magnitude-mask decoder, noisy phase re-used
                     complex   : single decoder that maps directly to the compressed complex spectrum
    mask_activation  lsigmoid (learnable, beta=2, paper) | sigmoid (beta=1, fixed) | relu
"""
from __future__ import annotations

import torch
import torch.nn as nn

from .blocks import DenseBlock, LearnableSigmoid, TFBlock


class DenseEncoder(nn.Module):
    def __init__(self, in_ch: int, ch: int):
        super().__init__()
        self.inp = nn.Sequential(nn.Conv2d(in_ch, ch, 1), nn.InstanceNorm2d(ch, affine=True), nn.PReLU(ch))
        self.dense = DenseBlock(ch, depth=4)
        self.down = nn.Sequential(nn.Conv2d(ch, ch, (1, 3), stride=(1, 2)),
                                  nn.InstanceNorm2d(ch, affine=True), nn.PReLU(ch))

    def forward(self, x):
        return self.down(self.dense(self.inp(x)))


class MaskDecoder(nn.Module):
    def __init__(self, ch: int, n_freq: int, activation: str = "lsigmoid", beta: float = 2.0):
        super().__init__()
        self.dense = DenseBlock(ch, depth=4)
        self.up = nn.ConvTranspose2d(ch, ch, (1, 3), stride=(1, 2))
        self.out = nn.Sequential(nn.Conv2d(ch, 1, 1), nn.InstanceNorm2d(1, affine=True), nn.PReLU(1),
                                 nn.Conv2d(1, 1, 1))
        if activation == "lsigmoid":
            self.act = LearnableSigmoid(n_freq, beta=beta, learnable=True)
        elif activation == "sigmoid":
            self.act = LearnableSigmoid(n_freq, beta=1.0, learnable=False)
        elif activation == "relu":
            self.act = nn.ReLU()
        else:
            raise ValueError(activation)

    def forward(self, x):  # -> (B, T, F)
        x = self.out(self.up(self.dense(x))).squeeze(1)
        return self.act(x)


class PhaseDecoder(nn.Module):
    """Predicts pseudo real/imag parts; phase = atan2 (parallel phase estimation)."""

    def __init__(self, ch: int, out_ch: int = 1):
        super().__init__()
        self.dense = DenseBlock(ch, depth=4)
        self.up = nn.Sequential(nn.ConvTranspose2d(ch, ch, (1, 3), stride=(1, 2)),
                                nn.InstanceNorm2d(ch, affine=True), nn.PReLU(ch))
        self.r = nn.Conv2d(ch, out_ch, 1)
        self.i = nn.Conv2d(ch, out_ch, 1)

    def forward(self, x):  # -> real, imag  (B, T, F)
        x = self.up(self.dense(x))
        return self.r(x).squeeze(1), self.i(x).squeeze(1)


class Generator(nn.Module):
    def __init__(self, n_freq: int = 201, dense_channel: int = 64, num_tf_blocks: int = 4,
                 tf_block: str = "conformer", decoder: str = "parallel",
                 mask_activation: str = "lsigmoid", lsigmoid_beta: float = 2.0,
                 conformer: dict | None = None):
        super().__init__()
        assert decoder in {"parallel", "mag_only", "complex"}
        self.decoder_type = decoder
        conformer = dict(conformer or {})
        self.encoder = DenseEncoder(2, dense_channel)
        if tf_block == "none" or num_tf_blocks == 0:
            self.tf_blocks = nn.Identity()
        else:
            kw = conformer if tf_block == "conformer" else {"dropout": conformer.get("dropout", 0.0)}
            self.tf_blocks = nn.Sequential(*[TFBlock(dense_channel, tf_block, **kw) for _ in range(num_tf_blocks)])
        if decoder in {"parallel", "mag_only"}:
            self.mask_decoder = MaskDecoder(dense_channel, n_freq, mask_activation, lsigmoid_beta)
        if decoder == "parallel":
            self.phase_decoder = PhaseDecoder(dense_channel)
        if decoder == "complex":
            self.complex_decoder = PhaseDecoder(dense_channel)  # same topology, outputs real/imag

    def forward(self, noisy_mag: torch.Tensor, noisy_pha: torch.Tensor):
        """noisy_mag / noisy_pha: (B, F, T) compressed magnitude and phase.

        Returns enhanced compressed magnitude (B,F,T), phase (B,F,T), complex (B,F,T,2).
        """
        mag_in = noisy_mag.transpose(1, 2)  # (B, T, F)
        pha_in = noisy_pha.transpose(1, 2)
        x = torch.stack([mag_in, pha_in], dim=1)  # (B, 2, T, F)
        x = self.tf_blocks(self.encoder(x))

        if self.decoder_type == "complex":
            r, i = self.complex_decoder(x)
            mag = torch.sqrt(r.pow(2) + i.pow(2) + 1e-9)
            pha = torch.atan2(i + 1e-10, r + 1e-5)
        else:
            mag = mag_in * self.mask_decoder(x)
            if self.decoder_type == "parallel":
                r, i = self.phase_decoder(x)
                pha = torch.atan2(i + 1e-10, r + 1e-5)
            else:
                pha = pha_in
        mag, pha = mag.transpose(1, 2), pha.transpose(1, 2)
        com = torch.stack((mag * torch.cos(pha), mag * torch.sin(pha)), dim=-1)
        return mag, pha, com


def build_generator(cfg, n_freq: int) -> Generator:
    m = cfg.model
    return Generator(n_freq=n_freq, dense_channel=m.dense_channel, num_tf_blocks=m.num_tf_blocks,
                     tf_block=m.tf_block, decoder=m.decoder, mask_activation=m.mask_activation,
                     lsigmoid_beta=m.get("lsigmoid_beta", 2.0), conformer=m.get("conformer"))
