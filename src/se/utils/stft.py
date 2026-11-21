"""STFT helpers with power-law magnitude compression (as in MP-SENet / CMGAN)."""
from __future__ import annotations

import torch


class STFT:
    """Compressed magnitude / phase analysis and synthesis.

    ``mag_c = |X| ** compress_factor``. All tensors are ``(B, F, T)``;
    the complex representation is ``(B, F, T, 2)`` = ``mag_c * [cos, sin]``.
    """

    def __init__(self, n_fft: int = 400, hop_length: int = 100, win_length: int = 400,
                 compress_factor: float = 0.3):
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.win_length = win_length
        self.compress_factor = compress_factor
        self._windows: dict[tuple, torch.Tensor] = {}

    @property
    def n_freq(self) -> int:
        return self.n_fft // 2 + 1

    def window(self, device: torch.device, dtype: torch.dtype = torch.float32) -> torch.Tensor:
        key = (device, dtype)
        if key not in self._windows:
            self._windows[key] = torch.hann_window(self.win_length, device=device, dtype=dtype)
        return self._windows[key]

    def complex_stft(self, wav: torch.Tensor) -> torch.Tensor:
        return torch.stft(wav, self.n_fft, hop_length=self.hop_length, win_length=self.win_length,
                          window=self.window(wav.device), center=True, pad_mode="reflect",
                          normalized=False, return_complex=True)

    def analysis(self, wav: torch.Tensor):
        """wav (B, L) -> mag_c, pha, com  with shapes (B,F,T), (B,F,T), (B,F,T,2)."""
        spec = self.complex_stft(wav)
        real, imag = spec.real, spec.imag
        mag = torch.sqrt(real.pow(2) + imag.pow(2) + 1e-9)
        pha = torch.atan2(imag + 1e-10, real + 1e-5)
        mag = torch.pow(mag, self.compress_factor)
        com = torch.stack((mag * torch.cos(pha), mag * torch.sin(pha)), dim=-1)
        return mag, pha, com

    def synthesis(self, mag_c: torch.Tensor, pha: torch.Tensor, length: int | None = None) -> torch.Tensor:
        mag = torch.pow(mag_c.clamp_min(0.0), 1.0 / self.compress_factor)
        spec = torch.complex(mag * torch.cos(pha), mag * torch.sin(pha))
        return torch.istft(spec, self.n_fft, hop_length=self.hop_length, win_length=self.win_length,
                           window=self.window(mag.device), center=True, length=length)

    @classmethod
    def from_config(cls, cfg) -> "STFT":
        return cls(cfg.n_fft, cfg.hop_length, cfg.win_length, cfg.compress_factor)
