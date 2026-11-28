#!/bin/bash
# Run every experiment listed in configs/experiments.txt as a SLURM job array.
#   sbatch --array=0-6%1 slurm/ablation_array.sbatch           # the 7 core runs, one at a time
#   EXPERIMENTS=configs/experiments_full.txt sbatch --array=0-13%1 ...   # all 14 (incl. future-work runs)
#   EPOCHS=30 sbatch --array=0-6%1 slurm/ablation_array.sbatch # longer schedule (default: 10 epochs)
# Email on end/failure: sbatch --mail-user=you@example.com ...
#SBATCH --job-name=se-ablation
#SBATCH --partition=amperenodes-medium
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --mail-type=END,FAIL

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p logs
source slurm/env.sh

mapfile -t CONFIGS < "${EXPERIMENTS:-configs/experiments.txt}"
CONFIG=${CONFIGS[$SLURM_ARRAY_TASK_ID]}
EXTRA=()
if [[ -n "${EPOCHS:-}" ]]; then EXTRA+=("train.epochs=${EPOCHS}"); fi

echo "[slurm] task=$SLURM_ARRAY_TASK_ID config=$CONFIG ${EXTRA[*]:-}"
python -m se.train --config "$CONFIG" train.num_workers=4 ${EXTRA[@]+"${EXTRA[@]}"}
