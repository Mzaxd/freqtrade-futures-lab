#!/usr/bin/env bash
# Adverse funding-rate stress: build a mirrored data dir where every funding
# rate is 2x the real value (same sign => always against the crowd side),
# then run the strategy on it. Usage: ./scripts/funding_adverse_test.sh STRATEGY TIMERANGE TAG
set -euo pipefail
cd "$(dirname "$0")/.."

STRATEGY="$1"; TIMERANGE="$2"; TAG="$3"
SRC="user_data/data/binance/futures"
DST="user_data/data_stress/binance/futures"

rm -rf user_data/data_stress
mkdir -p "$DST"
for f in "$SRC"/*.feather; do
  base=$(basename "$f")
  if [[ "$base" == *funding_rate* ]]; then
    .venv/bin/python - "$f" "$DST/$base" <<'EOF'
import sys
import pandas as pd
src, dst = sys.argv[1], sys.argv[2]
df = pd.read_feather(src)
df["funding_rate"] = df["funding_rate"] * 2.0
df.to_feather(dst)
EOF
  else
    ln -s "../../../data/binance/futures/$base" "$DST/$base"
  fi
done

./scripts/run_backtest.sh "$STRATEGY" "$TIMERANGE" "$TAG" --datadir "$DST"
