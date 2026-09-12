#!/usr/bin/env bash
# Phase-7 S3 new-coin batch: 11 fresh coins x {control, A, D, Fusion}, pool window.
set -euo pipefail
cd "$(dirname "$0")/.."

PAIRS=(
  ATOM/USDT:USDT FIL/USDT:USDT VET/USDT:USDT ETC/USDT:USDT XLM/USDT:USDT TRX/USDT:USDT
  BCH/USDT:USDT THETA/USDT:USDT IOTA/USDT:USDT AAVE/USDT:USDT NEAR/USDT:USDT
)

./scripts/opt7_s3_run.sh Supertrend      20210101-20240101 new11_ctrl "${PAIRS[@]}"
./scripts/opt7_s3_run.sh OPT7_SuperDD_A  20210101-20240101 new11_A    "${PAIRS[@]}"
./scripts/opt7_s3_run.sh OPT7_SuperDD_D  20210101-20240101 new11_D    "${PAIRS[@]}"
./scripts/opt7_s3_run.sh OPT7_SuperFusion 20210101-20240101 new11_F   "${PAIRS[@]}"
echo "ALL NEW11 DONE"
