# Speech Enhancement: MP-SENet Ablation Study

Final project for the **Speech Processing** course (HCMUS, Master's program), research track.

This repository contains:

1. **Literature review** of recent speech-enhancement papers (TASLP, Interspeech, NeurIPS, ICLR): see [`docs/literature_review.md`](docs/literature_review.md)
2. **Demo:** the official MP-SENet pretrained model ([`scripts/demo_official_mpsenet.sh`](scripts/demo_official_mpsenet.sh)), plus our own enhancement script and a notebook for listening to the ablation runs
3. **Ablation study:** a clean re-implementation of MP-SENet (Lu et al., Interspeech 2023) with config switches for 10 ablations: [`docs/ablation_design.md`](docs/ablation_design.md)
4. **Proposed improvements:** a multi-resolution STFT loss and perceptual contrast stretching (PCS) of the target, evaluated like the ablations

Report: [`docs/report/report.pdf`](docs/report/report.pdf) · Slides: [`docs/slides/slides.pdf`](docs/slides/slides.pdf)

## Team

| Student ID | Name | Tasks |
|---|---|---|
| 25C15036 | Chau Kien Dat | literature survey, demo, slides, video |
| 25C15043 | Nguyen Vi Khang | re-implementation, HPC ablation runs, evaluation, report |

## Repository layout

```
se-ablation/
├── configs/
│   ├── base.yaml               # full MP-SENet-style baseline (a00)
│   ├── debug.yaml              # tiny CPU smoke test
│   ├── experiments.txt         # the 7 core runs used by the SLURM array / local runner
│   ├── experiments_full.txt    # all 14 runs (incl. future-work ablations)
│   └── ablation/               # a01–a10 ablations, p01–p03 proposed improvements (one factor each)
├── src/se/
│   ├── data/                   # paired VoiceBank-DEMAND dataset, speaker-held-out validation split
│   ├── models/                 # generator (dense encoder, TS-Conformer, mag/phase decoders), metric discriminator
│   ├── losses/                 # magnitude, anti-wrapping phase, complex, time, consistency, metric-GAN, MR-STFT
│   ├── metrics/                # PESQ, CSIG/CBAK/COVL, SSNR, STOI/ESTOI, SI-SDR
│   ├── utils/                  # config system, STFT, PCS
│   ├── train.py                # training (single GPU or DDP via torchrun), auto-resume
│   ├── evaluate.py             # full test-set evaluation -> per_file.csv + summary.json
│   ├── enhance.py              # enhance any wav file / folder
│   └── inference.py
├── scripts/
│   ├── prepare_vbd.py          # download + resample VoiceBank-DEMAND to 16 kHz
│   ├── make_dummy_data.py      # synthetic data for smoke tests
│   ├── run_ablation_local.sh   # run every experiment sequentially (no SLURM)
│   ├── collect_results.py      # -> results/ablation_results.{csv,md}, ablation_pesq.png
│   ├── score_dir.py            # score any folder of enhanced wavs with our metrics
│   └── demo_official_mpsenet.sh
├── slurm/                      # sbatch scripts for HPC (single run, job array, DDP, noisy baseline)
├── notebooks/demo.ipynb        # listen + spectrograms + metrics for a few utterances
├── docs/                       # literature review, ablation design, report, slides
├── results/                    # aggregated results (filled after training)
└── tests/                      # pytest unit tests (shapes, losses, metrics, config)
```

## 1. Installation

```bash
git clone <this-repo-url> se-ablation && cd se-ablation
python -m venv .venv && source .venv/bin/activate          # or: conda env create -f environment.yml
pip install torch --index-url https://download.pytorch.org/whl/cu121   # match your CUDA version
pip install -e ".[dev]"
pytest -q                                                   # ~20 tests, CPU only
```

`pesq` builds from source and needs a C compiler (`gcc` on Linux; *MSVC Build Tools* on Windows).

## 2. Data

```bash
python scripts/prepare_vbd.py --out data      # ~2.5 GB download, resampled 48 kHz -> 16 kHz
```
This creates `data/voicebank_demand_16k/{clean,noisy}_{trainset_28spk,testset}_wav/`. If the download URLs change,
download the four zips manually from https://datashare.ed.ac.uk/handle/10283/2791 into `data/raw/` and run the script with `--skip_download`.

## 3. Smoke test (CPU, about a minute on a normal machine)

```bash
python scripts/make_dummy_data.py --out data/dummy
python -m se.train --config configs/debug.yaml
```

## 4. Training and ablation

Any config value can be overridden from the command line with dotted keys.

```bash
# one run (auto-evaluates best.pt on the test set when it finishes)
python -m se.train --config configs/base.yaml
python -m se.train --config configs/ablation/a03_mag_only.yaml train.epochs=50

# multi-GPU on one node (batch_size is per GPU)
torchrun --standalone --nproc_per_node=4 -m se.train --config configs/base.yaml
```

### On an HPC cluster (SLURM)

`slurm/env.sh` activates `./.venv` if present, otherwise the conda env `hcmus-sh` (override with `CONDA_ENV=...`). Add any `module load` lines your cluster needs there. Then edit the `#SBATCH` partition lines and run:

```bash
sbatch slurm/eval_noisy.sbatch                         # reference row: unprocessed noisy input
sbatch --array=0-6%1 slurm/ablation_array.sbatch       # the 7 core runs (configs/experiments.txt), one at a time
EPOCHS=30 sbatch --array=0-6%1 slurm/ablation_array.sbatch   # longer schedule (default: 5 epochs)
EXPERIMENTS=configs/experiments_full.txt sbatch --array=0-13%1 slurm/ablation_array.sbatch   # all 14, incl. future work
```
Jobs resume automatically from `runs/<name>/checkpoints/last.pt`, so a job that hits the time limit can just be resubmitted.

**Compute estimate:** every run trains for 5 epochs by default (`train.epochs` in `configs/base.yaml`): about
1.5 h on an A100 or 3–4 h on a P100 for runs with the metric GAN (11.5k × 2 s segments, batch 4). PESQ for the discriminator is computed on the CPU, so give
each job ≥ 8 CPU cores. The paper trains far longer, so absolute scores are lower, but all runs share the same budget.

### Collect results

```bash
python scripts/collect_results.py      # -> results/ablation_results.csv / .md / ablation_pesq.png
```

## 5. Evaluation, inference and demo

```bash
python -m se.evaluate --ckpt runs/a00_baseline/checkpoints/best.pt --save_wavs
python -m se.enhance  --ckpt runs/a00_baseline/checkpoints/best.pt --input my_noisy.wav --output out/

# official MP-SENet code + pretrained checkpoint, scored with our metric suite
bash scripts/demo_official_mpsenet.sh data/voicebank_demand_16k

# listen to and compare the ablation runs
jupyter notebook notebooks/demo.ipynb
```

## 6. Experiments

Core runs (`configs/experiments.txt`, 7 runs): one ablation per main idea of MP-SENet, plus our two proposals.

| ID | Change w.r.t. baseline |
|---|---|
| a00 | full model (MP-SENet-style, 2.05 M params) |
| a01 | no metric discriminator |
| a02 | no anti-wrapping phase losses |
| a03 | magnitude-only decoder (noisy phase) |
| a04 | BiLSTM instead of Conformer |
| p01 | **+ multi-resolution STFT loss** (proposed) |
| p02 | **+ PCS target** (proposed) |

Future work: implemented with a config each, not run in our budget (`configs/experiments_full.txt` runs everything):
a05 no STFT consistency loss · a06 no time + complex losses · a07 complex-mapping decoder ·
a08 no magnitude compression (c = 1) · a09 2 TS-Conformer blocks · a10 plain sigmoid mask · p03 P1 + P2 combined.

The result table is generated into `results/ablation_results.md` after the runs finish. To put the numbers into
the slides, run `python docs/slides/build_slides.py` (it reads that CSV), then export the PDF (see `docs/slides/README.md`).

## 7. Rebuilding the report and slides

Both are generated from code and fill in the results automatically from `results/ablation_results.csv`.

```bash
pip install -e ".[slides]"
python docs/report/build_report.py                      # figures + docs/report/report.docx
powershell -File docs/report/export_pdf.ps1             # Windows + Word: update TOC, export report.pdf
```

```bash
python docs/slides/build_slides.py                      # -> docs/slides/slides.pptx (fills tables from results/ if present)
powershell -File docs/slides/export_pdf.ps1             # Windows + PowerPoint -> slides.pdf
# or: soffice --headless --convert-to pdf docs/slides/slides.pptx --outdir docs/slides
```

## Acknowledgements and references

* Y.-X. Lu, Y. Ai, Z.-H. Ling, *MP-SENet: A Speech Enhancement Model with Parallel Denoising of Magnitude and Phase Spectra*, Interspeech 2023. Official code: https://github.com/yxlu-0102/MP-SENet. This repo is an independent re-implementation for ablation purposes.
* S. Abdulatif, R. Cao, B. Yang, *CMGAN: Conformer-Based Metric-GAN for Monaural Speech Enhancement*, IEEE/ACM TASLP 2024.
* R. Chao et al., *An Investigation of Incorporating Mamba for Speech Enhancement*, IEEE SLT 2024 (PCS).
* C. Valentini-Botinhao et al., *Investigating RNN-based speech enhancement methods for noise-robust Text-to-Speech*, SSW 2016 (VoiceBank-DEMAND).
* Composite measures: Y. Hu, P. Loizou, *Evaluation of objective quality measures for speech enhancement*, IEEE TASLP 2008.

MIT License.
