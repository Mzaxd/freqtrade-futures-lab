"""uni/step5b — funding-rate backfill, POOL MEMBERS ONLY (2026-11-07, agent 2).

Scope tightening vs backfill.py (coordinator directive): fetch funding feathers
only for pairs actually admitted in the point-in-time snapshots
(universe_ext.csv distinct pairs = frozen12 + 113 new coins incl. RAYSOL;
never-admitted candidates PAXG/PONS/XAUT are skipped). Raw /fapi/v1/fundingRate,
feather byte-compatible with freqtrade's (date datetime64[us,UTC],
funding_rate float64). Deadline-guarded (25 min), per-pair failures recorded.
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
DEADLINE_S = 25 * 60
T0 = time.time()


def get(url, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ftlab/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1.5 * (a + 1))
            if a == tries - 1:
                raise


def pages_funding(sym, start_ms):
    rows, start = [], start_ms
    while True:
        q = f"symbol={urllib.parse.quote(sym)}&limit=1000&startTime={start}"
        batch = get(f"https://fapi.binance.com/fapi/v1/fundingRate?{q}")
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start = batch[-1]["fundingTime"] + 1
        if len(rows) > 60_000:
            break
        time.sleep(0.12)
    return rows


def main():
    ext = pd.read_csv(f"{HERE}/universe_ext.csv")
    frozen = {f"{c}/USDT:USDT" for c in
              "BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI".split()}
    pairs = sorted(set(ext["pair"]) | frozen)     # pool members only (125)
    stats, skipped_deadline = {}, []
    for i, p in enumerate(pairs):
        sym = p.split("/")[0] + "USDT"
        base = p.replace("/USDT:USDT", "_USDT_USDT")
        out = f"{DAT}/{base}-1h-funding_rate.feather"
        if os.path.exists(out):
            stats[p] = "exists"
            continue
        ohl = f"{DAT}/{base}-1h-futures.feather"
        if not os.path.exists(ohl):
            stats[p] = "no-ohlcv(SKIP)"
            continue
        if time.time() - T0 > DEADLINE_S:
            skipped_deadline.append(p)
            stats[p] = "deadline(SKIP)"
            continue
        try:
            start = int(pd.read_feather(ohl)["date"].iloc[0].timestamp() * 1000) - 8 * 3600_000
            rows = pages_funding(sym, start)
            if not rows:
                stats[p] = "empty"
                continue
            df = pd.DataFrame({
                "date": pd.to_datetime([r["fundingTime"] for r in rows], unit="ms", utc=True)
                        .astype("datetime64[us, UTC]"),
                "funding_rate": [float(r["fundingRate"]) for r in rows],
            })
            df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
            df.to_feather(out)
            stats[p] = f"{len(df)} rows [{df['date'].iloc[0].date()}..{df['date'].iloc[-1].date()}]"
        except Exception as e:
            stats[p] = f"ERR {str(e)[:80]}"
        time.sleep(0.15)
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(pairs)} elapsed {time.time()-T0:.0f}s", flush=True)
    bad = {k: v for k, v in stats.items()
           if v not in ("exists",) and not v.startswith(("rows", "25", "3", "4", "5", "6", "7"))
           or v.startswith("rows") is False and not v.startswith(("exists",))}
    print(f"done in {time.time()-T0:.0f}s; deadline-skipped: {skipped_deadline or 'none'}")
    print("non-ok:", {k: v for k, v in stats.items()
                      if not (v == 'exists' or ' rows [' in v)})
    with open(f"{HERE}/backfill2_report.json", "w") as f:
        json.dump({"elapsed_s": round(time.time() - T0, 1), "stats": stats,
                   "deadline_skipped": skipped_deadline}, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
