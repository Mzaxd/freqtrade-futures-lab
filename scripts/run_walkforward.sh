#!/usr/bin/env bash
# Walk-forward evaluation with FROZEN parameters (no per-window re-optimization:
# validates regime robustness of the chosen parameter set; documented limitation).
# Train 2y / test 6m, rolling by 6m. Usage: ./scripts/run_walkforward.sh STRATEGY
set -euo pipefail
cd "$(dirname "$0")/.."

STRATEGY="${1:?strategy name required}"

# test windows (6 months each); train window is the 24 months preceding each test window
WINDOWS=(
  "20220701-20230101"
  "20230101-20230701"
  "20230701-20240101"
  "20240101-20240701"
  "20240701-20250101"
  "20250101-20250701"
  "20250701-20260101"
  "20260101-20260701"
  "20260701-20260912"
)

for W in "${WINDOWS[@]}"; do
  TAG="wf_${W:0:6}"
  echo "=== walk-forward test window $W ==="
  ./scripts/run_backtest.sh "$STRATEGY" "$W" "$TAG" > /dev/null
done

# summarize all walk-forward windows
.venv/bin/python scripts/summarize_results.py "walkforward_${STRATEGY}" user_data/backtest_results/wf_*_"${STRATEGY}".zip
echo "walk-forward summary written to user_data/reports/summary_walkforward_${STRATEGY}.{csv,md}"
