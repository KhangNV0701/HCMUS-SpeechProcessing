#!/bin/bash
# Run every experiment listed in configs/experiments.txt as a SLURM job array.
#   sbatch --array=0-13 slurm/ablation_array.sbatch            # all 14 runs
#   sbatch --array=0-13%4 slurm/ablation_array.sbatch          # at most 4 GPUs at once
#   EPOCHS=50 sbatch --array=0-13 slurm/ablation_array.sbatch  # shorter schedule for all runs
#SBATCH --job-name=se-ablation
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=48:00:00
#SBATCH --output=logs/%x-%A_%a.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p logs
source slurm/env.sh

mapfile -t CONFIGS < configs/experiments.txt
CONFIG=${CONFIGS[$SLURM_ARRAY_TASK_ID]}
EXTRA=()
if [[ -n "${EPOCHS:-}" ]]; then EXTRA+=("train.epochs=${EPOCHS}"); fi

echo "[slurm] task=$SLURM_ARRAY_TASK_ID config=$CONFIG ${EXTRA[*]:-}"
python -m se.train --config "$CONFIG" train.num_workers=${SLURM_CPUS_PER_TASK:-8} ${EXTRA[@]+"${EXTRA[@]}"}
