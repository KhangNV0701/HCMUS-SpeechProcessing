"""Metric discriminator (MetricGAN-style) that learns to predict normalised PESQ."""
from __future__ import annotations

import torch
import torch.nn as nn
from torch.nn.utils import spectral_norm


class MetricDiscriminator(nn.Module):
    def __init__(self, ch: int = 16):
        super().__init__()

        def down(cin, cout):
            return [spectral_norm(nn.Conv2d(cin, cout, 4, 2, 1, bias=False)),
                    nn.InstanceNorm2d(cout, affine=True), nn.PReLU(cout)]

        self.net = nn.Sequential(
            *down(2, ch), *down(ch, ch * 2), *down(ch * 2, ch * 4), *down(ch * 4, ch * 8),
            nn.AdaptiveMaxPool2d(1), nn.Flatten(),
            spectral_norm(nn.Linear(ch * 8, ch * 4)), nn.Dropout(0.3), nn.PReLU(ch * 4),
            spectral_norm(nn.Linear(ch * 4, 1)),
        )
        self.slope = nn.Parameter(torch.ones(1))

    def forward(self, ref_mag: torch.Tensor, est_mag: torch.Tensor) -> torch.Tensor:
        """ref_mag / est_mag (B, F, T) -> predicted metric in (0, 1), shape (B, 1)."""
        x = torch.stack([ref_mag, est_mag], dim=1)
        return torch.sigmoid(self.slope * self.net(x))
