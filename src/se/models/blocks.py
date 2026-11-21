"""Building blocks: dilated DenseBlock, Conformer, dual-path TF blocks."""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------- misc
class LearnableSigmoid(nn.Module):
    """beta * sigmoid(slope_f * x) with one learnable slope per frequency bin."""

    def __init__(self, n_freq: int, beta: float = 2.0, learnable: bool = True):
        super().__init__()
        self.beta = beta
        slope = torch.ones(n_freq)
        self.slope = nn.Parameter(slope) if learnable else nn.Parameter(slope, requires_grad=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x (..., F)
        return self.beta * torch.sigmoid(self.slope * x)


class DenseBlock(nn.Module):
    """Dilated dense block operating on (B, C, T, F); dilation grows along time."""

    def __init__(self, channels: int = 64, kernel_size=(3, 3), depth: int = 4):
        super().__init__()
        self.layers = nn.ModuleList()
        for i in range(depth):
            dil = 2 ** i
            pad = (dil * (kernel_size[0] - 1) // 2, (kernel_size[1] - 1) // 2)
            self.layers.append(nn.Sequential(
                nn.Conv2d(channels * (i + 1), channels, kernel_size, dilation=(dil, 1), padding=pad),
                nn.InstanceNorm2d(channels, affine=True),
                nn.PReLU(channels),
            ))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skip = x
        for layer in self.layers:
            x = layer(skip)
            skip = torch.cat([x, skip], dim=1)
        return x


# ----------------------------------------------------------------- conformer
class FeedForward(nn.Module):
    def __init__(self, dim: int, mult: int = 4, dropout: float = 0.0):
        super().__init__()
        self.net = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, dim * mult), nn.SiLU(),
                                 nn.Dropout(dropout), nn.Linear(dim * mult, dim), nn.Dropout(dropout))

    def forward(self, x):
        return self.net(x)


class MHSA(nn.Module):
    """Multi-head self-attention using PyTorch SDPA (memory-efficient on long inputs)."""

    def __init__(self, dim: int, heads: int = 4, dropout: float = 0.0):
        super().__init__()
        assert dim % heads == 0
        self.heads = heads
        self.norm = nn.LayerNorm(dim)
        self.qkv = nn.Linear(dim, dim * 3, bias=False)
        self.proj = nn.Linear(dim, dim)
        self.attn_dropout = dropout
        self.out_dropout = nn.Dropout(dropout)

    def forward(self, x):  # (N, L, D)
        n, l, d = x.shape
        q, k, v = self.qkv(self.norm(x)).chunk(3, dim=-1)
        q, k, v = (t.view(n, l, self.heads, d // self.heads).transpose(1, 2) for t in (q, k, v))
        out = F.scaled_dot_product_attention(q, k, v, dropout_p=self.attn_dropout if self.training else 0.0)
        out = out.transpose(1, 2).reshape(n, l, d)
        return self.out_dropout(self.proj(out))


class ConvModule(nn.Module):
    def __init__(self, dim: int, kernel_size: int = 31, expansion: int = 2, dropout: float = 0.0):
        super().__init__()
        inner = dim * expansion
        self.norm = nn.LayerNorm(dim)
        self.pw1 = nn.Conv1d(dim, inner * 2, 1)
        self.dw = nn.Conv1d(inner, inner, kernel_size, padding=kernel_size // 2, groups=inner)
        self.bn = nn.BatchNorm1d(inner)
        self.pw2 = nn.Conv1d(inner, dim, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):  # (N, L, D)
        x = self.norm(x).transpose(1, 2)
        x = F.glu(self.pw1(x), dim=1)
        x = F.silu(self.bn(self.dw(x)))
        x = self.pw2(x).transpose(1, 2)
        return self.dropout(x)


class ConformerBlock(nn.Module):
    def __init__(self, dim: int, heads: int = 4, ff_mult: int = 4, conv_kernel: int = 31,
                 dropout: float = 0.2):
        super().__init__()
        self.ff1 = FeedForward(dim, ff_mult, dropout)
        self.attn = MHSA(dim, heads, dropout)
        self.conv = ConvModule(dim, conv_kernel, 2, dropout)
        self.ff2 = FeedForward(dim, ff_mult, dropout)
        self.norm = nn.LayerNorm(dim)

    def forward(self, x):
        x = x + 0.5 * self.ff1(x)
        x = x + self.attn(x)
        x = x + self.conv(x)
        x = x + 0.5 * self.ff2(x)
        return self.norm(x)


class BiLSTMBlock(nn.Module):
    """Ablation replacement for a Conformer: BiLSTM + projection + residual."""

    def __init__(self, dim: int, dropout: float = 0.0, **_):
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.rnn = nn.LSTM(dim, dim, batch_first=True, bidirectional=True)
        self.proj = nn.Linear(2 * dim, dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        y, _ = self.rnn(self.norm(x))
        return x + self.dropout(self.proj(y))


class TFBlock(nn.Module):
    """Time-then-frequency sequence modelling on (B, C, T, F) (two-stage block)."""

    def __init__(self, dim: int, kind: str = "conformer", **kw):
        super().__init__()
        block = {"conformer": ConformerBlock, "lstm": BiLSTMBlock}[kind]
        self.time = block(dim, **kw)
        self.freq = block(dim, **kw)

    def forward(self, x):
        b, c, t, f = x.shape
        x = x.permute(0, 3, 2, 1).reshape(b * f, t, c)
        x = self.time(x) + x
        x = x.view(b, f, t, c).permute(0, 2, 1, 3).reshape(b * t, f, c)
        x = self.freq(x) + x
        return x.view(b, t, f, c).permute(0, 3, 1, 2)
