#!/usr/bin/env bash
# Hyperopt - IN-SAMPLE ONLY (2021-2022). Usage: ./scripts/run_hyperopt.sh STRATEGY [EPOCHS] [LOSS]
set -euo pipefail
cd "$(dirname "$0")/.."

STRATEGY="${1:?strategy name required}"
EPOCHS="${2:-150}"
LOSS="${3:-SharpeHyperOptLoss}"
FT=".venv/bin/freqtrade"

mkdir -p user_data/hyperopt_results user_data/logs

# Fixed random seed for reproducibility; Sharpe loss for robustness;
# restricted spaces (no ROI / no trailing search) to limit overfitting.
"$FT" hyperopt \
  --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy "$STRATEGY" \
  --hyperopt-loss "$LOSS" \
  --spaces buy sell \
  --epochs "$EPOCHS" \
  --random-state 42 \
  --timerange 20210101-20230101 \
  2>&1 | tee "user_data/logs/hyperopt_${STRATEGY}.log" | tail -30
