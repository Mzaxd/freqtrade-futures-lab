#!/usr/bin/env sh
# ABN 自调度任务器：跑在 compose 栈内部，零 Unraid 插件、零宿主机 cron 依赖。
# 每日任务（UTC）：
#   00:10  数据增量刷新（Sleeve B funding 门控数据 + 真样本外数据积累；
#          opt_common 的 mtime 感知缓存让运行中的 B 免重启即读到新数据；
#          首次启动时即为全量下载，约 20-60 分钟）
#   00:40  组合监控（monitor_portfolio.py --once，经 compose 内网访问三实例）
# 容器重启后若当日任务未执行过会立即补跑一次。
set -u
cd /freqtrade || exit 1
mkdir -p deploy/monitor user_data/logs
LOG=deploy/monitor/scheduler.log

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$LOG"; tail -1 "$LOG"; }

run_refresh() {
  log "job start: data refresh"
  if freqtrade download-data --userdir user_data \
      --config user_data/configs/OPT7_config_12p.json \
      --timerange 20210101- --timeframes 1h 15m 5m 1d \
      --logfile user_data/logs/refresh_daily.log; then
    log "job ok: data refresh"
  else
    log "job FAIL: data refresh (see user_data/logs/refresh_daily.log)"
  fi
}

run_monitor() {
  log "job start: portfolio monitor"
  if [ -f deploy/.monitor_env ]; then
    # shellcheck disable=SC1091
    . ./deploy/.monitor_env
    export FT_API_USER FT_API_PASSWORD
  fi
  python deploy/monitor_portfolio.py --once \
    --bots http://sleeve-a-opt4:8080,http://sleeve-b-momregime:8080,http://sleeve-c-nfilite:8080 \
    >> deploy/monitor/cron.log 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    log "job ok: monitor (exit 0)"
  elif [ "$rc" -eq 2 ]; then
    log "job RED-LINE: monitor exit 2 (30d DD > 20%) — CHECK deploy/monitor/alerts.log"
  else
    log "job FAIL: monitor exit $rc (see deploy/monitor/cron.log)"
  fi
}

REFRESH_AT=10   # 00:10 UTC（比较用十进制分钟，10# 前缀防八进制解析）
MONITOR_AT=40   # 00:40 UTC
last_refresh=""
last_monitor=""

log "scheduler up (refresh 00:${REFRESH_AT}Z, monitor 00:${MONITOR_AT}Z)"
while :; do
  now=$((10#$(date -u +%H%M)))
  today=$(date -u +%F)
  if [ "$now" -ge "$REFRESH_AT" ] && [ "$last_refresh" != "$today" ]; then
    run_refresh; last_refresh=$today
  fi
  if [ "$now" -ge "$MONITOR_AT" ] && [ "$last_monitor" != "$today" ]; then
    run_monitor; last_monitor=$today
  fi
  sleep 300
done
