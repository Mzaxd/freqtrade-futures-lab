#!/usr/bin/env python3
"""ABN 组合权益监控（dry-run 部署配套，stdlib-only，日频定时任务用）。

轮询三个 freqtrade 实例的 REST API，聚合组合权益，把日频快照写入
deploy/monitor/equity_daily.csv，计算：
  - 30 天滚动回撤（停机红线口径，>20% = RED）
  - 从峰值回撤（慢衰减哨兵，>25% = REVIEW）
输出：stdout 日志 + deploy/monitor/alerts.log。

推荐用法（Unraid User Scripts 每日一次，或任何 cron）：
  python3 deploy/monitor_portfolio.py --once
凭据经环境变量 FT_API_USER / FT_API_PASSWORD（三个实例须一致——部署模板如此）。
退出码：0=正常/告警但未触线，2=RED（30 天回撤>20%，需要人工停机复盘），1=配置错误。

安全边界：本工具只与同机 freqtrade 实例通信，_assert_local_url 拒绝一切公网目标。
"""
from __future__ import annotations

import argparse
import base64
import csv
import ipaddress
import json
import os
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
MON_DIR = HERE / "monitor"
CSV_PATH = MON_DIR / "equity_daily.csv"
ALERT_LOG = MON_DIR / "alerts.log"

DEFAULT_BOTS = "http://127.0.0.1:8081,http://127.0.0.1:8082,http://127.0.0.1:8083"
RED_LINE_30D = -0.20   # 30 天滚动回撤停机红线（章程口径）
REVIEW_PEAK = -0.25    # 从峰值回撤人工复核哨兵


def _assert_local_url(url: str) -> None:
    """SSRF 边界校验：仅允许 http(s) 且解析后 IP 为 loopback/私网/链路本地。"""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"scheme not allowed: {p.scheme!r}")
    if p.username or p.password:
        raise ValueError("credentials in URL are not allowed")
    host = p.hostname or ""
    if not host:
        raise ValueError("missing host")
    try:
        infos = socket.getaddrinfo(host, p.port or 80)
    except OSError as e:
        raise ValueError(f"unresolvable host: {host}") from e
    for _, _, _, _, sa in infos:
        ip = ipaddress.ip_address(sa[0])
        if not (ip.is_loopback or ip.is_private or ip.is_link_local):
            raise ValueError(f"non-local target blocked (SSRF guard): {host} -> {ip}")


def http_json(url: str, token: str | None = None, timeout: int = 30) -> dict:
    _assert_local_url(url)
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def login(base_url: str, user: str, password: str) -> str:
    url = base_url.rstrip("/") + "/api/v1/token/login"
    _assert_local_url(url)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"{user}:{password}".encode()).decode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["access_token"]


def bot_equity(base_url: str, user: str, password: str) -> float | None:
    """dry-run 实例的总权益（wallet + 持仓，USDT）。失败返回 None（不中断其它实例）。"""
    try:
        token = login(base_url, user, password)
        bal = http_json(base_url + "/api/v1/balance", token)
        return float(bal["total"]) if bal.get("total") is not None else None
    except Exception as e:  # noqa: BLE001 - 监控必须容错
        print(f"[warn] {base_url}: {e}")
        return None


def drawdowns(history: list[dict]) -> tuple[float, float, str]:
    """(30d 滚动回撤, 从峰值回撤, 最深点日期)。权益缺失日跳过。"""
    rows = [r for r in history if r.get("total")]
    if len(rows) < 2:
        return 0.0, 0.0, "-"
    eq = [float(r["total"]) for r in rows]
    dates = [r["date"] for r in rows]
    peaks, peak = [], eq[0]
    for v in eq:
        peak = max(peak, v)
        peaks.append(peak)
    i_worst = min(range(len(eq)), key=lambda i: eq[i] / peaks[i])
    dd_peak = eq[i_worst] / peaks[i_worst] - 1
    dd30 = 0.0
    for i in range(len(eq)):
        win_peak = max(eq[max(0, i - 30):i + 1])
        dd30 = min(dd30, eq[i] / win_peak - 1)
    return dd30, dd_peak, dates[i_worst]


def write_history(history: list[dict]) -> None:
    MON_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "a", "b", "c", "total"])
        w.writeheader()
        for r in sorted(history, key=lambda r: r["date"]):
            w.writerow(r)


def poll_once(bots: list[str], user: str, password: str) -> int:
    """单次轮询三实例 -> 写当日快照 -> 输出状态。返回进程退出码。"""
    now = datetime.now(timezone.utc)
    vals = [bot_equity(b, user, password) for b in bots]
    ok = [v for v in vals if v is not None]
    if len(ok) != len(bots) or len(bots) != 3:
        print(f"{now:%Y-%m-%d %H:%M:%S} UTC  [warn] unreachable bots: "
              f"{len(bots) - len(ok)}/{len(bots)}（快照未写入，次日重试）", flush=True)
        return 0
    today = now.date().isoformat()
    history = [r for r in csv.DictReader(CSV_PATH.open())] if CSV_PATH.exists() else []
    history = [r for r in history if r["date"] != today]  # 当日覆盖
    history.append({"date": today, "a": f"{vals[0]:.2f}", "b": f"{vals[1]:.2f}",
                    "c": f"{vals[2]:.2f}", "total": f"{sum(vals):.2f}"})
    write_history(history)
    dd30, dd_peak, worst_date = drawdowns(history)
    status = "OK"
    if dd30 <= RED_LINE_30D:
        status = "RED-STOP (30d rolling DD > 20%)"
    elif dd_peak <= REVIEW_PEAK:
        status = "REVIEW (from-peak DD > 25%)"
    line = (f"{now:%Y-%m-%d %H:%M:%S} UTC  equity A={vals[0]:.0f} B={vals[1]:.0f} "
            f"C={vals[2]:.0f} total={sum(vals):.0f}  dd30={dd30:+.1%} "
            f"ddPeak={dd_peak:+.1%}(worst {worst_date})  {status}")
    print(line, flush=True)
    if status != "OK":
        with ALERT_LOG.open("a") as f:
            f.write(line + "\n")
    return 2 if status.startswith("RED") else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", default=DEFAULT_BOTS, help="逗号分隔的三个 REST base url")
    ap.add_argument("--once", action="store_true", help="单次模式（cron 推荐）")
    ap.add_argument("--interval", type=int, default=3600, help="常驻模式轮询间隔")
    args = ap.parse_args()
    bots = [b.strip() for b in args.bots.split(",") if b.strip()]
    user = os.environ.get("FT_API_USER", "")
    password = os.environ.get("FT_API_PASSWORD", "")
    if not user or not password:
        print("FT_API_USER / FT_API_PASSWORD not set", file=sys.stderr)
        return 1
    if args.once:
        return poll_once(bots, user, password)
    print(f"monitoring {len(bots)} bots, interval {args.interval}s", flush=True)
    while True:
        poll_once(bots, user, password)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
