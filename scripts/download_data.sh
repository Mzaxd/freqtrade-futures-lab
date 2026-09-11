#!/usr/bin/env bash
# Download Binance USDT-perpetual data for backtesting.
# OHLCV + mark price + funding rates (futures mode downloads all three automatically).
# Usage: ./scripts/download_data.sh [START] [END]   (dates as YYYYMMDD)
set -euo pipefail
cd "$(dirname "$0")/.."

START="${1:-20190101}"
END="${2:-20260912}"
FT=".venv/bin/freqtrade"

mkdir -p user_data/logs

# Fast timeframes first (used by strategies), then fine timeframes for completeness.
$FT download-data --userdir user_data \
  --config user_data/configs/config_futures.json \
  --timerange "${START}-${END}" \
  --timeframes 1d 4h 1h \
  --logfile user_data/logs/download_htf.log

$FT download-data --userdir user_data \
  --config user_data/configs/config_futures.json \
  --timerange "${START}-${END}" \
  --timeframes 15m 5m \
  --logfile user_data/logs/download_ltf.log

echo "Download complete: BTC/ETH/SOL USDT-perp 5m 15m 1h 4h 1d + funding + mark, ${START}-${END}"
