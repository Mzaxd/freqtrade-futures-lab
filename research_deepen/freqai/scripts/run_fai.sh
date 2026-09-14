#!/usr/bin/env bash
# research_deepen/freqai runner: backtest FAI_V1 -> archive zip (content-verified).
# Usage: scripts/run_fai.sh TIMERANGE THRESHOLD TAG [EXTRA_ARGS...]
#   env FAI_THRESHOLD=THRESHOLD; zip archived as results/fai_${TAG}.zip
#   log at results/logs/fai_${TAG}.log
# Archive step verifies embedded strategy name == FAI_V1 AND freqai.identifier == fai_v1
# (parallel agents share user_data/backtest_results, newest-zip is not safe).
set -euo pipefail
cd "$(dirname "$0")/../../.."

TIMERANGE="$1"; THR="$2"; TAG="$3"; IDENTARG="$2"; shift 3
FT="research_deepen/freqai/.venv-freqai/Scripts/freqtrade.exe"
PY="research_deepen/freqai/.venv-freqai/Scripts/python.exe"
OUT="research_deepen/freqai/results"
LOG="$OUT/logs/fai_${TAG}.log"
mkdir -p "$OUT/logs"

FAI_THRESHOLD="$THR" "$FT" backtesting \
  --userdir user_data \
  --config research_deepen/freqai/configs/fai_base.json \
  --strategy-path research_deepen/freqai/strategies \
  --strategy FAI_V1 \
  --timerange "$TIMERANGE" \
  --export trades \
  --cache none \
  "$@" > "$LOG" 2>&1

SRC=$("$PY" - FAI_V1 fai_v1 <<'PYEOF'
import sys, glob, os, zipfile, json
strat, ident = sys.argv[1], sys.argv[2]
cands = sorted(glob.glob('user_data/backtest_results/backtest-result-*.zip'),
               key=os.path.getmtime, reverse=True)
for f in cands[:40]:
    try:
        with zipfile.ZipFile(f) as z:
            jname = [n for n in z.namelist()
                     if n.endswith('.json') and 'config' not in n and 'market' not in n][0]
            data = json.loads(z.read(jname))
        if (strat in data['strategy']
                and data['strategy'][strat].get('freqai_identifier', ident) == ident):
            print(f)
            break
    except Exception:
        continue
PYEOF
)
if [ -z "$SRC" ]; then echo "ERROR: no result zip found for FAI_V1/$IDENTARG" >&2; exit 1; fi
DEST="$OUT/fai_${TAG}.zip"
mv "$SRC" "$DEST"
echo "result saved: $DEST"
