"""Download VoiceBank-DEMAND (Valentini-Botinhao et al., 2016) and resample 48 kHz -> 16 kHz.

    python scripts/prepare_vbd.py --out data              # download + extract + resample
    python scripts/prepare_vbd.py --out data --skip_download   # zips/folders already in data/raw

Result:
    data/voicebank_demand_16k/{clean,noisy}_trainset_28spk_wav/*.wav   (11 572 pairs)
    data/voicebank_demand_16k/{clean,noisy}_testset_wav/*.wav          (824 pairs)

Dataset licence: CC BY 4.0, https://datashare.ed.ac.uk/handle/10283/2791
"""
from __future__ import annotations

import argparse
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

BASE_URL = "https://datashare.ed.ac.uk/bitstream/handle/10283/2791/"
SUBSETS = ["clean_trainset_28spk_wav", "noisy_trainset_28spk_wav", "clean_testset_wav", "noisy_testset_wav"]


def download(url: str, dst: Path) -> None:
    if dst.exists():
        print(f"[skip] {dst.name} already downloaded")
        return
    print(f"[download] {url}")
    tmp = dst.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dst)


def _resample(args):
    src, dst, target_sr = args
    if dst.exists():
        return
    wav, sr = sf.read(str(src), dtype="float32")
    if sr != target_sr:
        g = np.gcd(sr, target_sr)
        wav = resample_poly(wav, target_sr // g, sr // g).astype(np.float32)
    sf.write(str(dst), wav, target_sr, subtype="PCM_16")


def find_wav_dir(raw: Path, subset: str) -> Path:
    # zips sometimes extract to raw/<subset>/ or raw/<subset>/<subset>/
    for cand in [raw / subset / subset, raw / subset]:
        if cand.is_dir() and any(cand.glob("*.wav")):
            return cand
    raise FileNotFoundError(f"cannot find extracted wavs for {subset} under {raw}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--sr", type=int, default=16000)
    ap.add_argument("--skip_download", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    out = Path(args.out)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    dst_root = out / f"voicebank_demand_{args.sr // 1000}k"

    for subset in SUBSETS:
        zpath = raw / f"{subset}.zip"
        if not args.skip_download:
            download(BASE_URL + f"{subset}.zip", zpath)
        if zpath.exists() and not (raw / subset).exists():
            print(f"[extract] {zpath.name}")
            with zipfile.ZipFile(zpath) as z:
                z.extractall(raw / subset)
        src_dir = find_wav_dir(raw, subset)
        dst_dir = dst_root / subset
        dst_dir.mkdir(parents=True, exist_ok=True)
        jobs = [(p, dst_dir / p.name, args.sr) for p in sorted(src_dir.glob("*.wav"))]
        print(f"[resample] {subset}: {len(jobs)} files -> {dst_dir}")
        with ProcessPoolExecutor(args.workers) as ex:
            list(ex.map(_resample, jobs, chunksize=32))
    print(f"[done] data in {dst_root}")


if __name__ == "__main__":
    main()
