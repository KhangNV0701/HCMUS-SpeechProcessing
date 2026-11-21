#!/usr/bin/env bash
# Demo (part 2 of the assignment): run the AUTHORS' official MP-SENet code and
# pretrained VoiceBank-DEMAND checkpoint, then score it with OUR metric suite.
#   bash scripts/demo_official_mpsenet.sh [data_root]
# Upstream: https://github.com/yxlu-0102/MP-SENet (check its README if paths change).
set -euo pipefail
DATA=${1:-data/voicebank_demand_16k}
mkdir -p third_party demo_outputs
if [[ ! -d third_party/MP-SENet ]]; then
  git clone --depth 1 https://github.com/yxlu-0102/MP-SENet.git third_party/MP-SENet
fi
CKPT=$(ls third_party/MP-SENet/best_ckpt/g_best_vb* 2>/dev/null | head -n1 || true)
if [[ -z "$CKPT" ]]; then
  echo "Pretrained checkpoint not found under third_party/MP-SENet/best_ckpt; see the upstream README." >&2
  exit 1
fi
mkdir -p demo_outputs/official_mpsenet
OUT=$(realpath demo_outputs/official_mpsenet)
CLEAN=$(realpath "$DATA/clean_testset_wav")
NOISY=$(realpath "$DATA/noisy_testset_wav")
pushd third_party/MP-SENet >/dev/null
python inference.py --checkpoint_file "best_ckpt/$(basename "$CKPT")" \
  --input_clean_wavs_dir "$CLEAN" \
  --input_noisy_wavs_dir "$NOISY" \
  --output_dir "$OUT"
popd >/dev/null
python scripts/score_dir.py --clean "$DATA/clean_testset_wav" --enhanced "$OUT" --out demo_outputs/official_mpsenet_metrics
