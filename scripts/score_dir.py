"""Score a directory of enhanced wavs against clean references with our metric suite.

Useful to compare third-party systems (e.g. official MP-SENet / CMGAN outputs) on equal terms.

    python scripts/score_dir.py --clean data/voicebank_demand_16k/clean_testset_wav \
        --enhanced demo_outputs/official_mpsenet --out demo_outputs/official_mpsenet_metrics
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tqdm import tqdm

from se.data import load_wav
from se.evaluate import _metrics_job, _summarise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", required=True)
    ap.add_argument("--enhanced", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sr", type=int, default=16000)
    ap.add_argument("--num_workers", type=int, default=8)
    args = ap.parse_args()
    clean_dir, enh_dir = Path(args.clean), Path(args.enhanced)
    jobs = []
    for e in sorted(enh_dir.glob("*.wav")):
        c = clean_dir / e.name
        if c.exists():
            jobs.append((e.stem, load_wav(c, args.sr), load_wav(e, args.sr), args.sr))
    print(f"[score] {len(jobs)} pairs")
    with ProcessPoolExecutor(args.num_workers) as ex:
        rows = list(tqdm(ex.map(_metrics_job, jobs, chunksize=8), total=len(jobs)))
    _summarise(rows, Path(args.out), {"checkpoint": str(enh_dir)})


if __name__ == "__main__":
    main()
