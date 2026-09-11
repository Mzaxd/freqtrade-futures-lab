#!/usr/bin/env python
"""Build freqtrade-compatible funding_rate feather files from Binance public archives.

Why: the fapi /fundingRate REST endpoint returns 403 (WAF) for ccxt-based bulk
requests from this host, while data.binance.vision archives and single curl
requests work. This script:
  1. downloads monthly fundingRate zips from data.binance.vision (official),
  2. fetches the remaining tail from the REST endpoint (works with plain curl),
  3. writes ``<SYM>_USDT_USDT-1h-funding_rate.feather`` (columns: date, funding_rate)
     matching the format freqtrade 2026.8 itself writes (8h-native rows, hourly
     file naming used by freqtrade's funding_fee_timeframe='1h' on binance).

Usage: python scripts/build_funding_from_vision.py SOL 2020-09 2026-08 [--out user_data/data/binance/futures]
"""
from __future__ import annotations

import io
import sys
import zipfile
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "user_data/data/binance/futures"


def curl_bytes(url: str) -> bytes:
    r = subprocess.run(["curl", "-sS", "--fail", "-m", "60", url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed ({r.returncode}): {url}\n{r.stderr.decode()[:200]}")
    return r.stdout


def month_iter(start: str, end: str):
    y, m = int(start.split("-")[0]), int(start.split("-")[1])
    ey, em = int(end.split("-")[0]), int(end.split("-")[1])
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_archive(symbol: str, month: str) -> pd.DataFrame | None:
    url = (f"https://data.binance.vision/data/futures/um/monthly/fundingRate/"
           f"{symbol}/{symbol}-fundingRate-{month}.zip")
    try:
        raw = curl_bytes(url)
    except RuntimeError:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            df = pd.read_csv(f)
    df.columns = [c.strip().lower() for c in df.columns]
    ts_col = "calc_time" if "calc_time" in df.columns else "funding_time" if "funding_time" in df.columns else df.columns[0]
    rate_col = "last_funding_rate" if "last_funding_rate" in df.columns else df.columns[-1]
    out = pd.DataFrame({
        "ts_ms": df[ts_col].astype("int64"),
        "funding_rate": df[rate_col].astype(float),
    })
    return out


def fetch_rest_tail(symbol: str, start_ms: int) -> pd.DataFrame:
    url = (f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}"
           f"&startTime={start_ms}&limit=1000")
    import json
    rows = json.loads(curl_bytes(url).decode())
    if not rows:
        return pd.DataFrame(columns=["ts_ms", "funding_rate"])
    return pd.DataFrame({
        "ts_ms": [int(r["fundingTime"]) for r in rows],
        "funding_rate": [float(r["fundingRate"]) for r in rows],
    })


def build(symbol: str, start_month: str, end_month: str, out_dir: Path) -> Path:
    parts = []
    for month in month_iter(start_month, end_month):
        df = fetch_archive(symbol, month)
        if df is not None and len(df):
            parts.append(df)
    if not parts:
        raise RuntimeError(f"no archive data fetched for {symbol}")
    last_ts = max(p["ts_ms"].max() for p in parts)
    tail = fetch_rest_tail(symbol, last_ts + 1)
    if len(tail):
        parts.append(tail)

    allf = pd.concat(parts, ignore_index=True)
    # Floor the millisecond jitter to the hour so timestamps align to candle dates.
    allf["date"] = (allf["ts_ms"] // 3_600_000 * 3_600_000)
    allf = (allf.drop_duplicates(subset="date")
                 .sort_values("date"))
    allf["date"] = pd.to_datetime(allf["date"], unit="ms", utc=True)
    out = allf[["date", "funding_rate"]].reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    freqtrade_name = symbol.replace("USDT", "_USDT_USDT", 1) if symbol.endswith("USDT") else symbol
    dest = out_dir / f"{freqtrade_name}-1h-funding_rate.feather"
    out.to_feather(dest)
    print(f"{symbol}: {len(out)} funding rows {out['date'].iloc[0]} -> {out['date'].iloc[-1]} -> {dest}")
    return dest


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "SOLUSDT"
    start = sys.argv[2] if len(sys.argv) > 2 else "2020-09"
    end = sys.argv[3] if len(sys.argv) > 3 else "2026-08"
    outdir = Path(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_OUT
    build(sym, start, end, outdir)
