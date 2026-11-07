#!/bin/zsh
# CRASH IS runs — pre-registered variants V1-V6, window 20210101-20240101 (pre_reg.md §4)
set -e
cd /Users/caihaohan/Code/freqtrade-futures-lab
mkdir -p research_improve/logs
for v in crash_RVfroz crash_RVrank crash_RVpause crash_DDband crash_RV_DD crash_DDband65; do
  echo "=== $v $(date +%H:%M:%S) ==="
  .venv/bin/freqtrade backtesting --userdir user_data \
    --config user_data/configs/config_futures.json \
    --strategy-path user_data/strategies/oss \
    --strategy "$v" --timerange 20210101-20240101 \
    --max-open-trades 3 -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
    --dry-run-wallet 7000 --cache none \
    --export trades --export-filename "user_data/backtest_results/${v}_is.zip" \
    > "research_improve/logs/${v}_is.log" 2>&1
  echo "done $v $(date +%H:%M:%S) $(grep -o 'Total profit %.*' research_improve/logs/${v}_is.log | head -1)"
done
echo ALL_DONE
