#!/usr/bin/env bash
# hptB_run_cells.sh — run the pre-registered OAT mini-grid IS backtests
# (research_ab Hyperopt-B).  Three streams run concurrently; each backtest is
# capped at 25 min (DNF recorded) because some always-on cells make the
# position-adjustment storm pathologically slow.
# Usage: bash research_ab/scripts/hptB_run_cells.sh
set -u
cd /d/Code/AIQuant/freqtrade-futures-lab
export PYTHONPATH="D:\Code\AIQuant\freqtrade-futures-lab\user_data\strategies\oss"
UD=research_ab/hptB_userdir

CAP=1500   # seconds per backtest

run_cell () {
  local cell="$1"
  local log="research_ab/logs/hptB_cell_${cell}_IS.log"
  timeout "$CAP" .venv/Scripts/freqtrade.exe backtesting \
    --userdir "$UD" -c user_data/configs/OPT7_config_12p.json -c research_ab/hptB_config_overlay.json \
    --strategy-path research_ab/strategies \
    --strategy "$cell" --timerange 20210101-20240101 \
    -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
    --export trades --cache none > "$log" 2>&1
  local rc=$?
  if [ $rc -eq 124 ]; then
    echo "$cell TIMEOUT" >> research_ab/results/hptB_cells_status.txt
  elif [ $rc -ne 0 ]; then
    echo "$cell ERROR($rc)" >> research_ab/results/hptB_cells_status.txt
  else
    local z
    z=$(ls -t "$UD"/backtest_results/*.zip 2>/dev/null | head -1)
    if [ -n "$z" ]; then
      mv "$z" "research_ab/results/hptB_cell_${cell}_IS.zip"
      echo "$cell OK" >> research_ab/results/hptB_cells_status.txt
    else
      echo "$cell NOZIP" >> research_ab/results/hptB_cells_status.txt
    fi
  fi
}

: > research_ab/results/hptB_cells_status.txt

# stream 1: REGIME_SMA
( for c in R50 R75 R125 R150; do run_cell "$c"; done ) &
p1=$!
# stream 2: PER_COIN_SMA + tolerance
( for c in P20 P30 P75 P100 Tm02 T0 Tp02; do run_cell "$c"; done ) &
p2=$!
# stream 3: funding + max position weight
( for c in F03 F08 F10 M30 M60; do run_cell "$c"; done ) &
p3=$!

wait $p1 $p2 $p3
echo "=== cell status ==="
cat research_ab/results/hptB_cells_status.txt
