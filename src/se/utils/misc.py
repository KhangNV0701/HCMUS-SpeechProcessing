from __future__ import annotations

import json
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.distributed as dist


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def count_parameters(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def rms_normalize(noisy: torch.Tensor, *others: torch.Tensor, eps: float = 1e-8):
    """Scale every item so that the noisy signal has unit RMS (MP-SENet convention).

    Returns the scaled tensors and the per-item factor ``(B, 1)`` needed to undo it.
    """
    factor = torch.sqrt(noisy.shape[-1] / (noisy.pow(2).sum(-1, keepdim=True) + eps))
    return (noisy * factor, *[o * factor for o in others], factor)


# ---------------------------------------------------------------- distributed
def dist_info():
    world = int(os.environ.get("WORLD_SIZE", 1))
    rank = int(os.environ.get("RANK", 0))
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    return world, rank, local_rank


def init_distributed():
    world, rank, local_rank = dist_info()
    if world > 1 and not dist.is_initialized():
        backend = "nccl" if torch.cuda.is_available() else "gloo"
        dist.init_process_group(backend=backend)
        if torch.cuda.is_available():
            torch.cuda.set_device(local_rank)
    return world, rank, local_rank


def is_main_process() -> bool:
    return dist_info()[1] == 0


def barrier():
    if dist.is_available() and dist.is_initialized():
        dist.barrier()


def write_json(obj, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
