#!/bin/bash
# Multi-GPU (single node) training with torchrun.  Note: batch_size is PER GPU.
#   sbatch slurm/train_ddp.sbatch configs/base.yaml
# Email on end/failure: sbatch --mail-user=you@example.com ...
#SBATCH --job-name=se-ddp
#SBATCH --partition=amperenodes-medium
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=20:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --mail-type=END,FAIL

set -euo pipefail
CONFIG=${1:?usage: sbatch slurm/train_ddp.sbatch <config.yaml> [overrides...]}
shift || true
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p logs
source slurm/env.sh
NGPU=$(nvidia-smi -L | wc -l)
torchrun --standalone --nproc_per_node="$NGPU" -m se.train --config "$CONFIG" train.num_workers=4 "$@"
