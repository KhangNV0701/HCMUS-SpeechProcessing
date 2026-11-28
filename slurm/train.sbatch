#!/bin/bash
# Train + evaluate ONE configuration.
#   sbatch slurm/train.sbatch configs/base.yaml [extra.overrides=...]
# Adjust partition / account / modules to your cluster.
# Email on end/failure: sbatch --mail-user=you@example.com ...
#SBATCH --job-name=se-train
#SBATCH --partition=amperenodes-medium
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=20:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --mail-type=END,FAIL

set -euo pipefail
CONFIG=${1:?usage: sbatch slurm/train.sbatch <config.yaml> [overrides...]}
shift || true

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p logs
source slurm/env.sh

echo "[slurm] host=$(hostname) config=$CONFIG overrides=$*"
nvidia-smi || true
# Re-submitting the same job resumes from runs/<name>/checkpoints/last.pt automatically.
python -m se.train --config "$CONFIG" train.num_workers=4 "$@"
