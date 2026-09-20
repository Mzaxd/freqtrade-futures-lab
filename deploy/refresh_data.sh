#!/usr/bin/env bash
# ABN dry-run 每日数据增量刷新。
# 作用：Sleeve B 的 funding 门控读取本地 funding feather（opt_common 设计），
# NAS 上必须每天增量更新才能让门控在 dry-run 中与回测行为一致。
# 建议通过 Unraid "User Scripts" 插件每日 00:10 运行。
set -euo pipefail
cd "$(dirname "$0")/.."

# freqtrade 官方镜像内已有 CLI；宿主机跑则用 .venv（参照仓库 README）
FT="docker compose -f deploy/docker-compose.abn.yml run --rm sleeve-a-opt4"
if command -v freqtrade >/dev/null 2>&1; then FT="freqtrade"; fi

$FT download-data --userdir user_data \
  --config user_data/configs/OPT7_config_12p.json \
  --timerange 20210101- \
  --timeframes 1h 15m 5m 1d \
  --logfile user_data/logs/refresh_daily.log

echo "refresh done: $(date -u +%FT%Y-%m-%dT%H:%M:%SZ)"
