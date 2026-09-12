#!/usr/bin/env bash
# Phase-7 S3 subwindow batch: 6 half-year windows x {control, A, D, Fusion} on 12 old coins.
set -euo pipefail
cd "$(dirname "$0")/.."

WINDOWS=(
  "21h1 20210101-20210701"
  "21h2 20210701-20220101"
  "22h1 20220101-20220701"
  "22h2 20220701-20230101"
  "23h1 20230101-20230701"
  "23h2 20230701-20240101"
)
STRATS=("Supertrend" "OPT7_SuperDD_A" "OPT7_SuperDD_D" "OPT7_SuperFusion")

for w in "${WINDOWS[@]}"; do
  # split without set --
  name="${w%% *}"
  range="${w##* }"
  for st in "${STRATS[@]}"; do
    echo "== window $name strategy $st =="
    ./scripts/opt7_s3_run.sh "$st" "$range" "sub_${name}" \
      BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT BNB/USDT:USDT XRP/USDT:USDT ADA/USDT:USDT \
      DOGE/USDT:USDT AVAX/USDT:USDT LINK/USDT:USDT DOT/USDT:USDT LTC/USDT:USDT UNI/USDT:USDT
  done
done
echo "ALL SUBWINDOWS DONE"
