#!/usr/bin/env bash
# Run one backtest and archive the result under a stable name.
# Usage: ./scripts/run_backtest.sh STRATEGY TIMERANGE TAG [extra freqtrade args...]
set -euo pipefail
cd "$(dirname "$0")/.."

STRATEGY="$1"; TIMERANGE="$2"; TAG="$3"; shift 3
FT=".venv/bin/freqtrade"
OUT="user_data/backtest_results"

"$FT" backtesting \
  --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  --export trades \
  --cache none \
  "$@" 2>&1 | tee "user_data/logs/bt_${TAG}_${STRATEGY}.log" | tail -5

# rename newest result to a stable name
LATEST=$(ls -t "$OUT"/backtest-result-*.zip | head -1)
DEST="$OUT/${TAG}_${STRATEGY}.zip"
mv "$LATEST" "$DEST"
echo "result saved: $DEST"
