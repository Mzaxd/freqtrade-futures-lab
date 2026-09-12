#!/usr/bin/env bash
# End-to-end pipeline: data -> regime detection -> sub-strategies -> router ->
# routing-gain -> walk-forward -> stress -> final OOS (the OOS step is guarded
# and only run with --oos, once, after everything else is frozen).
set -euo pipefail
cd "$(dirname "$0")/.."

FT=".venv/bin/freqtrade"

echo "=== [0/7] sanity: freqtrade version (expect 2026.8) ==="
"$FT" --version

echo "=== [1/7] data download (Binance USDT-perp; idempotent) ==="
bash scripts/download_data.sh 20190101 20260913

echo "=== [2/7] data quality report ==="
.venv/bin/python scripts/data_quality_report.py

echo "=== [3/7] regime detector: fit-free rules + export (causal series) ==="
# threshold selected on IS only; see user_data/reports/01_regime_detection.md
.venv/bin/python user_data/strategies/regime_detector.py eval --rules
.venv/bin/python user_data/strategies/regime_detector.py export --rules --start 2020-01-01

echo "=== [4/7] sub-strategy standalone + router: IS baseline ==="
for S in TrendLongSA TrendShortSA MeanRevSA RegimeRouter; do
  bash scripts/run_backtest.sh "$S" 20210101-20230101 "all_is_$(echo "$S" | tr 'A-Z' a-z)"
done

echo "=== [5/7] routing-gain test (VAL 2023-2024) ==="
for S in TrendLongSA TrendShortSA MeanRevSA RegimeRouter; do
  bash scripts/run_backtest.sh "$S" 20230101-20250101 "all_val_$(echo "$S" | tr 'A-Z' a-z)"
done
.venv/bin/python scripts/summarize_results.py routing_gain_rerun \
  user_data/backtest_results/all_val_*.zip

echo "=== [6/7] walk-forward (frozen params) + stress ==="
for W in 20230101-20230701 20230701-20240101 20240101-20240701 20240701-20250101; do
  bash scripts/run_backtest.sh RegimeRouter "$W" "wfr_${W:0:6}"
done
.venv/bin/python scripts/router_stress.py 20210101-20250101

echo "=== [7/7] done (development pipeline). ==="
echo "Final OOS (2025-01 -> 2026-09) is NOT run here. Run it ONCE, manually:"
echo "  bash scripts/run_backtest.sh RegimeRouter 20250101-20260912 oos_final"
