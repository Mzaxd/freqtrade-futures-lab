#!/usr/bin/env bash
# Phase-7 S3 runner: backtest -> archive zip under opt7_ prefix.
# Usage: scripts/opt7_s3_run.sh STRATEGY TIMERANGE TAG PAIRS...
#   zip archived as user_data/backtest_results/opt7_${TAG}_${STRATEGY}.zip
#   log at user_data/logs/opt7_s3_${TAG}_${STRATEGY}.log
# Archive step is content-verified (parallel agents share the results dir, so
# "newest zip" is not safe): we pick the newest backtest-result-*.zip whose
# embedded strategy name equals STRATEGY.
set -euo pipefail
cd "$(dirname "$0")/.."

STRATEGY="$1"; TIMERANGE="$2"; TAG="$3"; shift 3
FT=".venv/bin/freqtrade"
OUT="user_data/backtest_results"
LOG="user_data/logs/opt7_s3_${TAG}_${STRATEGY}.log"

"$FT" backtesting \
  --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  --export trades \
  --cache none \
  --pairs "$@" > "$LOG" 2>&1

SRC=$(.venv/bin/python - "$STRATEGY" <<'PYEOF'
import sys, glob, os, zipfile, json
strat = sys.argv[1]
cands = sorted(glob.glob('user_data/backtest_results/backtest-result-*.zip'),
               key=os.path.getmtime, reverse=True)
for f in cands[:40]:  # only recent ones; first match (newest) wins
    try:
        with zipfile.ZipFile(f) as z:
            jname = [n for n in z.namelist()
                     if n.endswith('.json') and 'config' not in n and 'market' not in n][0]
            data = json.loads(z.read(jname))
        if strat in data['strategy']:
            print(f)
            break
    except Exception:
        continue
PYEOF
)
if [ -z "$SRC" ]; then echo "ERROR: no result zip found for $STRATEGY" >&2; exit 1; fi
DEST="$OUT/opt7_${TAG}_${STRATEGY}.zip"
mv "$SRC" "$DEST"
echo "result saved: $DEST"
