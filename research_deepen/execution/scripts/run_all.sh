#!/usr/bin/env bash
# Reproduction runner for research_deepen/execution (EXE_OPT4 execution-model study).
# Run from repo root. Steps 1-2 are heavy (backtest ~2min, 1m download ~2min).
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root

FT=.venv/bin/freqtrade
PY=.venv/Scripts/python.exe
R=research_deepen/execution/results

# 1) baseline backtest (12 coins, 2021-01-01 .. 2024-01-01, charter boundary)
$FT backtesting --userdir user_data \
  --config user_data/configs/OPT7_config_12p.json \
  --strategy-path research_deepen/execution/strategies \
  --strategy EXE_OPT4 --timerange 20210101-20240101 \
  --export trades --cache none > $R/backtest_exe_opt4.log 2>&1

# zip hygiene: move the newest backtest-result-*.zip whose embedded strategy
# name is EXE_OPT4 into the sandbox (content-verified, see opt7_s3_run.sh)
$PY - <<'EOF'
import glob, os, zipfile, json, shutil
cands = sorted(glob.glob('user_data/backtest_results/backtest-result-*.zip'),
               key=os.path.getmtime, reverse=True)
for f in cands[:40]:
    try:
        with zipfile.ZipFile(f) as z:
            j = [n for n in z.namelist() if n.endswith('.json')
                 and 'config' not in n and 'market' not in n][0]
            if 'EXE_OPT4' in json.loads(z.read(j))['strategy']:
                shutil.move(f, 'research_deepen/execution/results/exe_opt4_baseline.zip')
                print('archived', f); break
    except Exception:
        continue
EOF

# 2) 1m data download (12 coins; ~19M rows, zero-gap verified)
$FT download-data --userdir user_data \
  --config user_data/configs/OPT7_config_12p.json \
  --timerange 20210101-20240101 --timeframes 1m > $R/download_1m.log 2>&1

# 3) analysis: extract trades -> entry sim -> stop slippage -> liq proximity -> stats
$PY research_deepen/execution/scripts/analyze_execution.py \
  --step all --zip $R/exe_opt4_baseline.zip | tee $R/analyze_all.log
