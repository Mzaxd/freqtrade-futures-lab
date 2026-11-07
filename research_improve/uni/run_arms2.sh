#!/bin/zsh
# uni arms runner (agent 2, pool-limited per coordinator directive) — usage:
#   run_arms2.sh <probe|a|b|c>
# probe = 2-day plumbing validation on the full 125-pair whitelist (0-info,
#         disclosed infrastructure probe, same class as predecessor's 2 probes)
# a = uni_ARL_frozen12  20210101-20261107  frozen12          (MOT4, wallet 7000)
# b = uni_ARL_ext       20230101-20261107  pool125 (frozen12 + PIT new) single shot
# c = uni_ARL_pit       20230101-20261107  pool125 (all gated)          single shot
set -e
cd /Users/caihaohan/Code/freqtrade-futures-lab
ARM=$1
FROZEN="BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT BNB/USDT:USDT XRP/USDT:USDT ADA/USDT:USDT DOGE/USDT:USDT AVAX/USDT:USDT LINK/USDT:USDT DOT/USDT:USDT LTC/USDT:USDT UNI/USDT:USDT"
POOL=$(tr '\n' ' ' < research_improve/uni/pool_pairs.txt)
case $ARM in
  probe) STRAT=uni_ARL_ext;     RANGE=20250110-20250112; PAIRS=$POOL;   LABEL=uni_probe_ext ;;
  a)     STRAT=uni_ARL_frozen12; RANGE=20210101-20261107; PAIRS=$FROZEN; LABEL=uni_full_a ;;
  b)     STRAT=uni_ARL_ext;     RANGE=20230101-20261107; PAIRS=$POOL;   LABEL=uni_oos_b ;;
  c)     STRAT=uni_ARL_pit;     RANGE=20230101-20261107; PAIRS=$POOL;   LABEL=uni_oos_c ;;
  *) echo "arm must be probe|a|b|c"; exit 1 ;;
esac
echo "=== $LABEL ($STRAT $RANGE, $(echo $PAIRS | wc -w | tr -d ' ') pairs) ==="
.venv/bin/freqtrade backtesting --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss \
  --strategy $STRAT --timerange $RANGE \
  --max-open-trades 4 -p $PAIRS \
  --dry-run-wallet 7000 --cache none \
  --export trades --export-filename user_data/backtest_results/${LABEL}.zip \
  > research_improve/logs/${LABEL}.log 2>&1
grep -E "Total trades|Absolute profit|Total profit %|Absolute Drawdown" research_improve/logs/${LABEL}.log | head -6
