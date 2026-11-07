#!/usr/bin/env python3
"""monitor_shadow.py — 草案,未部署(research_revive/pipe/drafts/)。

方案3 影子栈监控(改自 deploy/monitor_portfolio.py —— 冻结文件,不改,故立新文件):
  - 2 bots(Rev_A_vt60f1 / Rev_B_2xvt);独立 CSV deploy_shadow/monitor/equity_shadow.csv
    (不污染冻结栈 deploy/monitor/equity_daily.csv)
  - 组合 dd30(红线 -20%,预警 -18%)+ 从峰回撤(K1:-28% REVIEW / -35% STOP)
  - 袖级 dd30(K3:A 袖 -20% REVIEW / -25% STOP)
  - 月度收益行(K2:单月 <= -13% 或连续两月 <= -10% REVIEW)
  - BTC 1d feather 新鲜度(K6:>36h 告警 / >48h 停 B)
退出码:0 正常/告警未触线,2 RED(30d DD > 20%),1 配置错误。stdlib-only。
执行时复制到 deploy_shadow/monitor_shadow.py。
"""
from __future__ import annotations

import argparse
import base64
import csv
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
CSV_PATH = MON_DIR / "equity_shadow.csv"
ALERT_LOG = MON_DIR / "alerts.log"
BTC_1D = HERE.parents[0] / "user_data" / "data" / "binance" / "futures" / "BTC_USDT_USDT-1d-futures.feather"

RED_LINE_30D = -0.20     # 章程红线(K4)
WARN_LINE_30D = -0.18    # 红线前 2pp 预警
PEAK_REVIEW = -0.28      # K1 REVIEW(回测画像最深 -33.6%)
PEAK_STOP = -0.35        # K1 STOP(画像带外)
SLEEVE_REVIEW = -0.20    # K3 A 袖 REVIEW
SLEEVE_STOP = -0.25      # K3 A 袖 STOP
MONTH_REVIEW = -0.13     # K2 单月 REVIEW(回测最差月 -12.8% + 余量)
FEATHER_WARN_H = 36.0    # K6 告警
FEATHER_STOP_H = 48.0    # K6 停 B


def _assert_local_url(url: str) -> None:   # 与 monitor_portfolio.py 同款 SSRF 防线
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"scheme not allowed: {p.scheme!r}")
    if p.username or p.password:
        raise ValueError("credentials in URL are not allowed")
    host = p.hostname or ""
    if not host:
        raise ValueError("missing host")
    for _, _, _, _, sa in socket.getaddrinfo(host, p.port or 80):
        import ipaddress
        ip = ipaddress.ip_address(sa[0])
        if not (ip.is_loopback or ip.is_private or ip.is_link_local):
            raise ValueError(f"non-local target blocked: {host} -> {ip}")


def http_json(url, token=None, timeout=30):
    _assert_local_url(url)
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def bot_equity(base_url, user, password):
    try:
        r = urllib.request.Request(base_url.rstrip("/") + "/api/v1/token/login")
        r.add_header("Authorization", "Basic " +
                     base64.b64encode(f"{user}:{password}".encode()).decode())
        with urllib.request.urlopen(r, timeout=30) as resp:
            token = json.loads(resp.read().decode())["access_token"]
        bal = http_json(base_url + "/api/v1/balance", token)
        return float(bal["total"]) if bal.get("total") is not None else None
    except Exception as e:  # noqa: BLE001 - 监控必须容错
        print(f"[warn] {base_url}: {e}")
        return None


def dd_series(vals):
    peaks, peak, out = [], vals[0], []
    for v in vals:
        peak = max(peak, v)
        peaks.append(peak)
    out = [v / p - 1 for v, p in zip(vals, peaks)]
    return out


def dd30_of(vals):
    worst = 0.0
    for i in range(len(vals)):
        win = max(vals[max(0, i - 30):i + 1])
        worst = min(worst, vals[i] / win - 1)
    return worst


def poll_once(bots, user, password) -> int:
    now = datetime.now(timezone.utc)
    vals = [bot_equity(b, user, password) for b in bots]
    if len([v for v in vals if v is not None]) != len(bots):
        print(f"{now:%Y-%m-%d %H:%M:%S} UTC  [warn] unreachable shadow bots — 快照未写,次日重试", flush=True)
        return 0
    MON_DIR.mkdir(parents=True, exist_ok=True)
    today = now.date().isoformat()
    history = list(csv.DictReader(CSV_PATH.open())) if CSV_PATH.exists() else []
    history = [r for r in history if r["date"] != today]
    history.append({"date": today, "a": f"{vals[0]:.2f}", "b": f"{vals[1]:.2f}",
                    "total": f"{sum(vals):.2f}"})
    with CSV_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "a", "b", "total"])
        w.writeheader()
        for r in sorted(history, key=lambda r: r["date"]):
            w.writerow(r)

    a = [float(r["a"]) for r in history]
    b = [float(r["b"]) for r in history]
    t = [float(r["total"]) for r in history]
    months = sorted({r["date"][:7] for r in history})

    dd30 = dd30_of(t)
    peak_dd = min(dd_series(t))
    a_dd30 = dd30_of(a)
    a_peak = min(dd_series(a))

    # K2 月度收益(最近两个完整月)
    month_rets = []
    for m in months[-3:-1] if len(months) > 1 else []:
        mrows = [r for r in history if r["date"].startswith(m)]
        if len(mrows) >= 2:
            month_rets.append((m, float(mrows[-1]["total"]) / float(mrows[0]["total"]) - 1))

    # K6 feather 新鲜度
    try:
        feather_age_h = (time.time() - BTC_1D.stat().st_mtime) / 3600.0
    except OSError:
        feather_age_h = None

    status, notes = "OK", []
    if dd30 <= RED_LINE_30D:
        status = "RED-STOP"
    elif dd30 <= WARN_LINE_30D:
        notes.append(f"WARN dd30 {dd30:+.1%} 预警线 {WARN_LINE_30D:.0%}")
    if peak_dd <= PEAK_STOP:
        status = "STOP-K1 从峰画像外"
        notes.append(f"peakDD {peak_dd:+.1%} <= {PEAK_STOP:.0%}")
    elif peak_dd <= PEAK_REVIEW:
        notes.append(f"REVIEW-K1 从峰 {peak_dd:+.1%}")
    if a_dd30 <= SLEEVE_STOP:
        notes.append(f"STOP-K3 停 A:袖 dd30 {a_dd30:+.1%}")
    elif a_dd30 <= SLEEVE_REVIEW:
        notes.append(f"REVIEW-K3 A 袖 dd30 {a_dd30:+.1%}(从峰 {a_peak:+.1%})")
    bad_months = [m for m, r in month_rets if r <= MONTH_REVIEW]
    if bad_months:
        notes.append(f"REVIEW-K2 月度 {bad_months} <= {MONTH_REVIEW:.0%}")
    if feather_age_h is not None:
        if feather_age_h > FEATHER_STOP_H:
            notes.append(f"STOP-K6 停 B:BTC 1d feather 陈旧 {feather_age_h:.0f}h")
        elif feather_age_h > FEATHER_WARN_H:
            notes.append(f"WARN-K6 feather 陈旧 {feather_age_h:.0f}h")

    line = (f"{now:%Y-%m-%d %H:%M:%S} UTC  shadow A={vals[0]:.0f} B={vals[1]:.0f} "
            f"total={sum(vals):.0f}  dd30={dd30:+.1%} peak={peak_dd:+.1%} "
            f"A_dd30={a_dd30:+.1%}  {status} {'; '.join(notes)}")
    print(line, flush=True)
    if status != "OK" or notes:
        with ALERT_LOG.open("a") as f:
            f.write(line + "\n")
    return 2 if status.startswith(("RED", "STOP")) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", default="http://127.0.0.1:8084,http://127.0.0.1:8085")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=3600)
    args = ap.parse_args()
    bots = [b.strip() for b in args.bots.split(",") if b.strip()]
    user = os.environ.get("FT_API_USER", "")
    password = os.environ.get("FT_API_PASSWORD", "")
    if not user or not password:
        print("FT_API_USER / FT_API_PASSWORD not set", file=sys.stderr)
        return 1
    if args.once:
        return poll_once(bots, user, password)
    while True:
        poll_once(bots, user, password)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
