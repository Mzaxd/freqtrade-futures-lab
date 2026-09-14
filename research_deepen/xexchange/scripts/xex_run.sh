#!/usr/bin/env bash
# xexchange runner: backtest -> content-verified zip archive under results/.
# Usage: xex_run.sh STRATEGY CONFIG TIMERANGE TAG [extra freqtrade args...]
# Zip archived as research_deepen/xexchange/results/xex_${TAG}_${STRATEGY}.zip
# Archive step is content-verified (parallel agents share backtest_results/):
# we pick the newest backtest-result-*.zip whose embedded strategy name matches.
set -euo pipefail
cd "$(dirname "$0")/../../.."

STRATEGY="$1"; CONFIG="$2"; TIMERANGE="$3"; TAG="$4"; shift 4
FT=".venv/bin/freqtrade"
OUT="user_data/backtest_results"
RES="research_deepen/xexchange/results"
LOG="research_deepen/xexchange/scripts/bt_${TAG}_${STRATEGY}.log"

"$FT" backtesting \
  --userdir user_data \
  --config "$CONFIG" \
  --strategy-path research_deepen/xexchange/strategies \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  --export trades \
  --cache none \
  "$@" > "$LOG" 2>&1

SRC=$(.venv/bin/python - "$STRATEGY" <<'PYEOF'
import sys, glob, os, zipfile, json
strat = sys.argv[1]
cands = sorted(glob.glob('user_data/backtest_results/backtest-result-*.zip'),
               key=os.path.getmtime, reverse=True)
for f in cands[:60]:
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
DEST="$RES/xex_${TAG}_${STRATEGY}.zip"
mv "$SRC" "$DEST"
echo "result saved: $DEST"
