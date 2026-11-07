#!/bin/zsh
# uni arms runner — usage: run_arms.sh <IS|OOS> <arm...>
# IS  = 20210101-20240101 ; OOS = 20240101-20261107 (single shot per arm)
set -e
cd /Users/caihaohan/Code/freqtrade-futures-lab
PHASE=$1; shift
case $PHASE in
  IS)  RANGE=20210101-20240101 ;;
  OOS) RANGE=20240101-20261107 ;;
  *)   echo "phase must be IS|OOS"; exit 1 ;;
esac
FROZEN="BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT BNB/USDT:USDT XRP/USDT:USDT ADA/USDT:USDT DOGE/USDT:USDT AVAX/USDT:USDT LINK/USDT:USDT DOT/USDT:USDT LTC/USDT:USDT UNI/USDT:USDT"
NEW=$(grep -v RAYSOL research_improve/uni/candidate_pairs.txt | tr '\n' ' ')
for ARM in "$@"; do
  case $ARM in
    a) STRAT=uni_ARL_frozen12; PAIRS=$FROZEN ;;
    b) STRAT=uni_ARL_ext;      PAIRS="$FROZEN $NEW RAYSOL/USDT:USDT" ;;
    c) STRAT=uni_ARL_pit;      PAIRS="$FROZEN $NEW RAYSOL/USDT:USDT" ;;
    *) echo "arm must be a|b|c"; exit 1 ;;
  esac
  LABEL=uni_${PHASE}_${ARM}
  echo "=== $LABEL ($STRAT) ==="
  .venv/bin/freqtrade backtesting --userdir user_data \
    --config user_data/configs/config_futures.json \
    --strategy-path user_data/strategies/oss \
    --strategy $STRAT --timerange $RANGE \
    --max-open-trades 4 -p $PAIRS \
    --dry-run-wallet 7000 --cache none \
    --export trades --export-filename user_data/backtest_results/${LABEL}.zip \
    > research_improve/logs/${LABEL}.log 2>&1
  grep -E "Total trades|Absolute profit|Total profit %|drawdown" research_improve/logs/${LABEL}.log | head -6
done
