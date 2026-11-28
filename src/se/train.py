"""Train an MP-SENet-style model (single GPU or DDP via ``torchrun``).

Example:
    python -m se.train --config configs/base.yaml
    python -m se.train --config configs/ablation/a01_no_metric_disc.yaml train.epochs=50
    torchrun --nproc_per_node=4 -m se.train --config configs/base.yaml
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import time
from pathlib import Path

import numpy as np
import torch
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler, Subset
from tqdm import tqdm

from .data import PairedDataset, build_splits
from .inference import _enhance_segment
from .losses import GeneratorLoss, batch_pesq_normalized, init_pesq_pool, pesq_many
from .models import MetricDiscriminator, build_generator
from .utils import STFT, load_config, save_config
from .utils.misc import (barrier, count_parameters, init_distributed, is_main_process,
                         seed_everything, write_json)


def set_requires_grad(module: torch.nn.Module, flag: bool) -> None:
    for p in module.parameters():
        p.requires_grad_(flag)


def unwrap(m):
    return m.module if isinstance(m, DDP) else m


@torch.no_grad()
def validate(generator, stft, loader, device, sr, use_pesq=True):
    generator.eval()
    g = unwrap(generator)
    pairs, mag_losses = [], []
    for clean, noisy, _ in loader:
        clean, noisy = clean.to(device), noisy.to(device)
        est = _enhance_segment(g, stft, noisy)
        c_mag, _, _ = stft.analysis(clean)
        e_mag, _, _ = stft.analysis(est)
        mag_losses.append(torch.nn.functional.mse_loss(c_mag, e_mag).item())
        if use_pesq:
            pairs.append((clean[0].cpu().numpy(), est[0].cpu().numpy()))
    pesqs = [p for p in pesq_many(pairs, sr) if p >= 0] if pairs else []  # parallel if the pool is up
    generator.train()
    return {"val_mag_loss": float(np.mean(mag_losses)),
            "val_pesq": float(np.mean(pesqs)) if pesqs else float("nan")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--resume", default=None, help="path to last.pt (default: auto-resume if present)")
    ap.add_argument("overrides", nargs="*", help="dotted overrides, e.g. train.epochs=10")
    args = ap.parse_args(argv)

    cfg = load_config(args.config, args.overrides)
    world, rank, local_rank = init_distributed()
    device = torch.device(f"cuda:{local_rank}" if torch.cuda.is_available() else "cpu")
    seed_everything(cfg.experiment.seed + rank)

    out_dir = Path(cfg.experiment.output_dir) / cfg.experiment.name
    ckpt_dir = out_dir / "checkpoints"
    if is_main_process():
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        save_config(cfg, out_dir / "config.yaml")
    barrier()

    stft = STFT.from_config(cfg.stft)
    sr = cfg.data.sample_rate
    tc, lc = cfg.train, cfg.loss

    # ------------------------------------------------------------------ data
    train_pairs, val_pairs, _ = build_splits(cfg)
    if tc.get("max_train_files"):
        train_pairs = train_pairs[: tc.max_train_files]
    train_set = PairedDataset(train_pairs, sr, cfg.data.segment_seconds, train=True,
                              pcs=cfg.data.get("pcs", False), stft_cfg=cfg.stft)
    val_set = PairedDataset(val_pairs, sr, None, train=False)
    if tc.get("val_max_files"):
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(val_set))[: tc.val_max_files]
        val_set = Subset(val_set, sorted(idx.tolist()))
    sampler = DistributedSampler(train_set, shuffle=True) if world > 1 else None
    train_loader = DataLoader(train_set, batch_size=tc.batch_size, shuffle=sampler is None,
                              sampler=sampler, num_workers=tc.num_workers, pin_memory=True,
                              drop_last=True, persistent_workers=tc.num_workers > 0)
    val_loader = DataLoader(val_set, batch_size=1, shuffle=False, num_workers=min(2, tc.num_workers))

    # ---------------------------------------------------------------- models
    generator = build_generator(cfg, stft.n_freq).to(device)
    use_gan = lc.get("metric", 0) > 0
    discriminator = MetricDiscriminator().to(device) if use_gan else None
    if tc.get("tf32", True) and device.type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True  # Ampere+ tensor cores for fp32 matmuls
        torch.backends.cudnn.allow_tf32 = True
    if use_gan or tc.get("val_pesq", True):
        init_pesq_pool(tc.get("pesq_workers", tc.batch_size))
    n_params = count_parameters(generator)
    if is_main_process():
        print(f"[se] generator parameters: {n_params / 1e6:.3f} M  | GAN: {use_gan}  | device: {device}")

    optim_g = torch.optim.AdamW(generator.parameters(), tc.lr, betas=tuple(tc.betas))
    sched_g = torch.optim.lr_scheduler.ExponentialLR(optim_g, gamma=tc.lr_decay)
    if use_gan:
        optim_d = torch.optim.AdamW(discriminator.parameters(), tc.lr, betas=tuple(tc.betas))
        sched_d = torch.optim.lr_scheduler.ExponentialLR(optim_d, gamma=tc.lr_decay)

    start_epoch, step, best = 0, 0, -math.inf
    resume = Path(args.resume) if args.resume else ckpt_dir / "last.pt"
    if resume.exists():
        state = torch.load(resume, map_location="cpu", weights_only=False)
        generator.load_state_dict(state["generator"])
        optim_g.load_state_dict(state["optim_g"])
        sched_g.load_state_dict(state["sched_g"])
        if use_gan and state.get("discriminator") is not None:
            discriminator.load_state_dict(state["discriminator"])
            optim_d.load_state_dict(state["optim_d"])
            sched_d.load_state_dict(state["sched_d"])
        start_epoch, step, best = state["epoch"] + 1, state["step"], state["best"]
        if is_main_process():
            print(f"[se] resumed from {resume} (epoch {start_epoch})")
        if start_epoch >= tc.epochs and (out_dir / "eval" / "summary.json").exists():
            if is_main_process():
                print(f"[se] {out_dir.name} already trained and evaluated, nothing to do")
            return

    if world > 1:
        generator = DDP(generator, device_ids=[local_rank] if device.type == "cuda" else None)
        if use_gan:
            discriminator = DDP(discriminator, device_ids=[local_rank] if device.type == "cuda" else None)

    criterion = GeneratorLoss(lc)
    log_path = out_dir / "train_log.csv"
    log_fields = None

    # ------------------------------------------------------------------ loop
    for epoch in range(start_epoch, tc.epochs):
        if sampler is not None:
            sampler.set_epoch(epoch)
        generator.train()
        t0 = time.time()
        pbar = tqdm(train_loader, disable=not is_main_process(), desc=f"epoch {epoch}", leave=False)
        running = {}
        for clean, noisy, _ in pbar:
            clean, noisy = clean.to(device, non_blocking=True), noisy.to(device, non_blocking=True)
            factor = torch.sqrt(noisy.shape[-1] / (noisy.pow(2).sum(-1, keepdim=True) + 1e-8))
            clean, noisy = clean * factor, noisy * factor

            clean_mag, clean_pha, clean_com = stft.analysis(clean)
            noisy_mag, noisy_pha, _ = stft.analysis(noisy)
            mag_g, pha_g, com_g = generator(noisy_mag, noisy_pha)
            wav_g = stft.synthesis(mag_g, pha_g, length=clean.shape[-1])
            _, _, com_g_hat = stft.analysis(wav_g)

            # ---- discriminator step
            loss_d = torch.zeros((), device=device)
            if use_gan:
                set_requires_grad(discriminator, True)
                optim_d.zero_grad(set_to_none=True)
                pesq_target = batch_pesq_normalized(clean, wav_g, sr)
                b = clean_mag.shape[0]
                ref = torch.cat([clean_mag, clean_mag], 0)
                est = torch.cat([clean_mag, mag_g.detach()], 0)
                d_out = discriminator(ref, est)
                d_real, d_fake = d_out[:b], d_out[b:]
                loss_d = torch.nn.functional.mse_loss(d_real, torch.ones_like(d_real))
                if pesq_target is not None:
                    loss_d = loss_d + torch.nn.functional.mse_loss(d_fake, pesq_target.to(device))
                else:  # keep DDP graph identical across ranks
                    loss_d = loss_d + 0.0 * d_fake.sum()
                loss_d.backward()
                optim_d.step()
                set_requires_grad(discriminator, False)

            # ---- generator step
            optim_g.zero_grad(set_to_none=True)
            # raw module (params frozen): avoids a second DDP forward without matching reduction
            metric_g = unwrap(discriminator)(clean_mag, mag_g) if use_gan else None
            loss_g, terms = criterion(clean_mag=clean_mag, clean_pha=clean_pha, clean_com=clean_com,
                                      clean_wav=clean, mag_g=mag_g, pha_g=pha_g, com_g=com_g,
                                      wav_g=wav_g, com_g_hat=com_g_hat, metric_g=metric_g)
            loss_g.backward()
            if tc.get("grad_clip", 0):
                torch.nn.utils.clip_grad_norm_(generator.parameters(), tc.grad_clip)
            optim_g.step()
            step += 1

            terms.update(loss_g=float(loss_g.detach()), loss_d=float(loss_d.detach()))
            for k, v in terms.items():
                running[k] = running.get(k, 0.0) + v
            if is_main_process() and step % tc.log_every == 0:
                pbar.set_postfix(g=f"{terms['loss_g']:.3f}", d=f"{terms['loss_d']:.3f}")

        sched_g.step()
        if use_gan:
            sched_d.step()

        # ---------------------------------------------------- end of epoch
        if is_main_process():
            n_batches = max(len(train_loader), 1)
            row = {"epoch": epoch, "step": step, "time_s": round(time.time() - t0, 1),
                   "lr": sched_g.get_last_lr()[0]}
            row.update({k: v / n_batches for k, v in running.items()})
            row.update(val_mag_loss=float("nan"), val_pesq=float("nan"))
            if (epoch + 1) % tc.val_every_epochs == 0 or epoch + 1 == tc.epochs:
                row.update(validate(generator, stft, val_loader, device, sr,
                                    use_pesq=tc.get("val_pesq", True)))
            score = row.get("val_pesq", float("nan"))
            if math.isnan(score):
                score = -row.get("val_mag_loss", math.inf)
            g_state = unwrap(generator).state_dict()
            if score > best:
                best = score
                torch.save({"generator": g_state, "config": cfg.to_dict(), "epoch": epoch,
                            "score": best, "n_params": n_params}, ckpt_dir / "best.pt.tmp")
                os.replace(ckpt_dir / "best.pt.tmp", ckpt_dir / "best.pt")
            torch.save({"generator": g_state, "optim_g": optim_g.state_dict(),
                        "sched_g": sched_g.state_dict(),
                        "discriminator": unwrap(discriminator).state_dict() if use_gan else None,
                        "optim_d": optim_d.state_dict() if use_gan else None,
                        "sched_d": sched_d.state_dict() if use_gan else None,
                        "config": cfg.to_dict(), "epoch": epoch, "step": step, "best": best,
                        "n_params": n_params}, ckpt_dir / "last.pt.tmp")
            # atomic: a job killed mid-write (time limit) never leaves a corrupt last.pt
            os.replace(ckpt_dir / "last.pt.tmp", ckpt_dir / "last.pt")
            if log_fields is None:
                log_fields = list(row.keys())
                new_file = not log_path.exists()
            else:
                new_file = False
            with open(log_path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=log_fields, extrasaction="ignore")
                if new_file:
                    w.writeheader()
                w.writerow(row)
            print("[se] " + " ".join(f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}"
                                     for k, v in row.items()))
        barrier()

    if is_main_process():
        write_json({"best_score": best, "n_params": n_params, "epochs": tc.epochs},
                   out_dir / "train_summary.json")
        if cfg.get("eval", {}).get("after_train", False):
            from .evaluate import evaluate_checkpoint

            evaluate_checkpoint(ckpt_dir / "best.pt", out_dir / "eval", device=device,
                                num_workers=cfg.eval.get("num_workers", 8),
                                save_wavs=cfg.eval.get("save_wavs", False),
                                chunk_seconds=cfg.eval.get("chunk_seconds"))
    barrier()


if __name__ == "__main__":
    main()
