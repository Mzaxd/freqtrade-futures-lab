"""uni/step2b — daily klines for ALL non-TRADING (settling/delisted) COIN
perpetuals enumerable via fapi exchangeInfo. Systematic delisted coverage for
the survivorship-bias disclosure (long-dead symbols absent from exchangeInfo
remain guess-based; see delisted_probe.json).
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DAILY = os.path.join(HERE, "daily")

with urllib.request.urlopen("https://fapi.binance.com/fapi/v1/exchangeInfo",
                            timeout=30) as r:
    ei = json.loads(r.read())

targets = [s for s in ei["symbols"]
           if s.get("status") not in ("TRADING", "PENDING_TRADING")
           and s.get("contractType") == "PERPETUAL"
           and s.get("underlyingType") == "COIN"
           and s["symbol"].endswith("USDT")]
print(f"non-trading COIN perps: {len(targets)}")

BASE = "https://fapi.binance.com/fapi/v1/klines"


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def fetch_1d(sym):
    rows, start = [], 0
    while True:
        batch = get(f"{BASE}?symbol={sym}&interval=1d&limit=1000&startTime={start}")
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start = batch[-1][0] + 1
        if len(rows) > 4000:
            break
    return rows


out_meta = {}
for s in targets:
    sym = s["symbol"]
    p = os.path.join(DAILY, f"{sym}.csv")
    if os.path.exists(p):
        out_meta[sym] = "already"
        continue
    try:
        rows = fetch_1d(sym)
    except Exception as e:
        out_meta[sym] = f"err:{str(e)[:40]}"
        continue
    if rows:
        out_meta[sym] = f"data:{len(rows)}d:{rows[0][0]}:{rows[-1][0]}"
        with open(p, "w") as f:
            f.write("date,open,high,low,close,volume,quote_volume\n")
            for r in rows:
                f.write(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[7]}\n")
    else:
        out_meta[sym] = "empty"

with open(os.path.join(HERE, "settling_meta.json"), "w") as f:
    json.dump({"symbols": {t["symbol"]: t.get("status") for t in targets},
               "fetch": out_meta}, f, indent=1)
n_data = sum(1 for v in out_meta.values() if v.startswith("data:"))
print(f"fetched daily for {n_data}/{len(targets)} settling perps")
