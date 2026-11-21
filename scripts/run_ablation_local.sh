#!/usr/bin/env bash
# Run all experiments sequentially on one machine (no SLURM).
#   bash scripts/run_ablation_local.sh            # full schedule from the configs
#   EPOCHS=30 bash scripts/run_ablation_local.sh  # shorter schedule
set -euo pipefail
EXTRA=()
if [[ -n "${EPOCHS:-}" ]]; then EXTRA+=("train.epochs=${EPOCHS}"); fi
python -m se.evaluate --noisy_baseline --config configs/base.yaml
while read -r cfg; do
  [[ -z "$cfg" ]] && continue
  echo "=== $cfg ==="
  python -m se.train --config "$cfg" ${EXTRA[@]+"${EXTRA[@]}"}
done < configs/experiments.txt
python scripts/collect_results.py
