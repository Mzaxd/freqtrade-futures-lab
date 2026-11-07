#!/usr/bin/env bash
# OPT9 forensic-optimization program (2026-11-01).
# Pre-registered sequence (order fixed BEFORE any OPT9 result was seen):
#   0. baseline reproduce   : OPT4 12p IS 2021-23, must match archived
#                             +1495.8% / DD 15.92% / 433 trades (tolerance:
#                             tiny diffs only from data-start differences)
#   1. ablations            : OPT9a (be_floor only), OPT9b (circuit only),
#                             OPT9c (time-stop exemption only)
#   2. combined             : OPT9 full stack
#   3. burned-window        : 2024-01..2026-09 disclosure regression for
#                             baseline + best variant (data already burned
#                             in phases 3-7; informative only)
#   4. stress               : fee x3 + delay1 on baseline + best variant
# Guards (accept only if ALL hold for the winner):
#   G1 maxDD <= 16.4% (baseline 15.92% + 0.5pp tolerance)
#   G2 six half-year slices 2021H1..2023H2 all positive
#   G3 top-20 winner profit sum >= 95% of baseline (fat tail intact)
#   G4 no falsified-direction reintroduction (entry/sizing untouched)
# Usage: ./scripts/opt9_run.sh STEP    (STEP in: base|ablate|combined|burn|stress)
set -euo pipefail
cd "$(dirname "$0")/.."

FT=".venv/bin/freqtrade"
OUT="user_data/backtest_results"
PAIRS=(BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT BNB/USDT:USDT XRP/USDT:USDT ADA/USDT:USDT \
       DOGE/USDT:USDT AVAX/USDT:USDT LINK/USDT:USDT DOT/USDT:USDT LTC/USDT:USDT UNI/USDT:USDT)
IS="20210101-20240101"
BURN="20240102-20260912"

run() {  # run STRATEGY TIMERANGE TAG [extra args...]
  local S="$1" T="$2" TAG="$3"; shift 3
  mkdir -p user_data/logs
  "$FT" backtesting --userdir user_data \
    --config user_data/configs/config_futures.json \
    --strategy-path user_data/strategies/oss \
    --strategy "$S" --timerange "$T" \
    --max-open-trades 4 -p "${PAIRS[@]}" \
    --export trades --cache none "$@" \
    > "user_data/logs/opt9_${TAG}.log" 2>&1 || { tail -20 "user_data/logs/opt9_${TAG}.log"; exit 1; }
  local LATEST DEST
  LATEST=$(ls -t "$OUT"/backtest-result-*.zip | head -1)
  DEST="$OUT/opt9_${TAG}.zip"
  mv "$LATEST" "$DEST"
  grep -E "Total profit |Absolute profit |Total/Daily Avg Prof|Sharpe|Sortino|Calmar|Max Drawdown|Profit factor|Total trades |Wins\/Draws\/Losses" "user_data/logs/opt9_${TAG}.log" | head -12
  echo "saved: $DEST"
}

case "${1:-}" in
  base)    run OPT4_VolatilitySystem "$IS" base_is; run OPT9_Off "$IS" off_is; run OPT8b_VolatilitySystem "$IS" opt8b_is ;;
  ablate)  run OPT9a_BEFloor "$IS" a_is; run OPT9b_Circuit "$IS" b_is; run OPT9c_Exempt "$IS" c_is; run OPT9d_BEFloor25 "$IS" d_is ;;
  combined) run OPT9_VolatilitySystem "$IS" full_is ;;
  round2)  run OPT9f_AsymExit "$IS" f_is; run OPT9g_ChainRisk "$IS" g_is; run OPT9h_EquityTier "$IS" h_is ;;
  burn)    run OPT4_VolatilitySystem "$BURN" base_burn; run OPT9_VolatilitySystem "$BURN" full_burn ;;
  stress)
    run OPT4_VolatilitySystem "$IS" base_fee3x --fee 0.0015
    run OPT9_VolatilitySystem "$IS" full_fee3x --fee 0.0015
    run Stress_OPT9_delay1 "$IS" full_delay1
    ;;
  *) echo "usage: $0 base|ablate|combined|burn|stress"; exit 1 ;;
esac
