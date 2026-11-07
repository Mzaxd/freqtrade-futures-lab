"""uni/step5 — backfill funding-rate (and OM ohlcv/mark) feathers via raw fapi.

freqtrade's bulk download hit a WAF block after the first few pairs (HTML 418
in its log); funding feathers are required (fail_without_data=True) so we
fetch /fapi/v1/fundingRate directly and write feathers byte-compatible with
freqtrade's (columns: date datetime64[us, UTC], funding_rate float64).
OM/USDT:USDT ohlcv+mark also failed in the bulk run -> fetched from
/fapi/v1/klines and /fapi/v1/markPriceKlines.
"""
import json
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = "/Users/caihaohan/Code/freqtrade-futures-lab"
DAT = f"{ROOT}/user_data/data/binance/futures"
HERE = f"{ROOT}/research_improve/uni"


def get(url, tries=5):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ftlab/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            time.sleep(2.0 * (a + 1))
            if a == tries - 1:
                raise


def pages(path, sym, start_ms, step_ms=None):
    """Paginate a kline-ish endpoint forward from start_ms."""
    rows, start = [], start_ms
    while True:
        q = f"symbol={urllib.parse.quote(sym)}&limit=1000&startTime={start}"
        batch = get(f"https://fapi.binance.com{path}?{q}")
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start = batch[-1][0] + (step_ms or 1)
        if len(rows) > 200_000:
            break
        time.sleep(0.15)
    return rows


def write_funding(sym):
    out = f"{DAT}/{sym.replace('USDT', '_USDT_USDT')}-1h-funding_rate.feather"
    if os.path.exists(out):
        return "exists"
    ohl = f"{DAT}/{sym.replace('USDT', '_USDT_USDT')}-1h-futures.feather"
    if not os.path.exists(ohl):
        return "no-ohlcv(yet)"
    start = int(pd.read_feather(ohl)["date"].iloc[0].timestamp() * 1000) - 8 * 3600_000
    rows = pages("/fapi/v1/fundingRate", sym, start)
    if not rows:
        return "empty"
    df = pd.DataFrame({
        "date": pd.to_datetime([r["fundingTime"] for r in rows], unit="ms", utc=True)
                .astype("datetime64[us, UTC]"),
        "funding_rate": [float(r["fundingRate"]) for r in rows],
    })
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df.to_feather(out)
    return f"{len(df)} rows"


def write_ohlcv_mark(sym):
    base = f"{DAT}/{sym.replace('USDT', '_USDT_USDT')}"
    ohl = f"{base}-1h-futures.feather"
    if not os.path.exists(ohl):
        # listing via onboardDate from active_meta
        meta = {r["ccxt_id"]: r["onboard_ms"] for r in
                json.load(open(f"{HERE}/active_meta.json"))}
        start = max(meta.get(sym, 0) - 3 * 3600_000, 0)
        for path, suffix in [("/fapi/v1/klines", "futures"),
                             ("/fapi/v1/markPriceKlines", "mark")]:
            rows = pages(path, sym, start)
            if not rows:
                return f"{suffix} empty"
            df = pd.DataFrame({
                "date": pd.to_datetime([r[0] for r in rows], unit="ms", utc=True)
                        .astype("datetime64[us, UTC]"),
                "open": [float(r[1]) for r in rows],
                "high": [float(r[2]) for r in rows],
                "low": [float(r[3]) for r in rows],
                "close": [float(r[4]) for r in rows],
                "volume": [float(r[5]) for r in rows],
            })
            df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
            df.to_feather(f"{base}-1h-{suffix}.feather")
            time.sleep(0.5)
    return "ok"


if __name__ == "__main__":
    pairs = [l.strip() for l in open(f"{HERE}/candidate_pairs.txt") if l.strip()]
    stats = {"funding": {}}
    for i, p in enumerate(pairs):
        sym = p.split("/")[0] + "USDT"
        try:
            stats["funding"][p] = write_funding(sym)
        except Exception as e:
            stats["funding"][p] = f"ERR {str(e)[:60]}"
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(pairs)}")
        time.sleep(0.2)
    missing = {k: v for k, v in stats["funding"].items() if v not in ("exists",) and not v.endswith("rows")}
    print("non-ok funding:", missing if missing else "none")
    with open(f"{HERE}/backfill_report.json", "w") as f:
        json.dump(stats, f, indent=1)
