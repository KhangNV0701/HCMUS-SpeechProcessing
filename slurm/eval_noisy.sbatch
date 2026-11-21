#!/bin/bash
# Metrics of the unprocessed noisy test set (reference row of the ablation table). CPU only.
#SBATCH --job-name=se-eval-noisy
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p logs
source slurm/env.sh
python -m se.evaluate --noisy_baseline --config configs/base.yaml --num_workers ${SLURM_CPUS_PER_TASK:-16}
