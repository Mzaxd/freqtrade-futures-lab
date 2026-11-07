"""uni/step2 — fetch daily klines for candidate ranking.

Inputs : active_meta.json (active COIN+Crypto USDT perps)
         + a bounded probe list of plausible DELISTED perp symbols
         (systematic S3 enumeration blocked by env proxy — disclosed).
Output : daily/<ccxt_id>.csv  cols: date,open,high,low,close,volume,quote_volume
         delisted_probe.json  (probe outcomes, for the disclosure section)

fapi/v1/klines retained data confirmed for some non-active symbols
(TOMOUSDT etc.) — whatever the probe recovers enters the same ranking.
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DAILY = os.path.join(HERE, "daily")
os.makedirs(DAILY, exist_ok=True)

with open(os.path.join(HERE, "active_meta.json")) as f:
    active = json.load(f)
active_ids = {r["ccxt_id"] for r in active}
CUTOFF = 1640995200000  # 2022-01-01

# --- bounded delisted probe list (spot-delisted / perp-settled guesses) ------
PROBE = ["TOMOUSDT", "UNFIUSDT", "TROYUSDT", "BONDUSDT", "NKNUSDT", "BALUSDT",
         "FLMUSDT", "LSKUSDT", "LUNAUSDT", "RAYUSDT", "ENJUSDT", "LRCUSDT",
         "SCUSDT", "STORJUSDT", "ICXUSDT", "XEMUSDT", "XNOUSDT", "WAVESUSDT",
         "BNTUSDT", "RENUSDT", "POLSUSDT", "TKOUSDT", "TRUUSDT", "MBLUSDT",
         "DENTUSDT", "ELFUSDT", "COMBOUSDT", "FIOUSDT", "GTOUSDT", "LOOMUSDT",
         "MDAUSDT", "OAXUSDT", "PAXGUSDT", "RAYSOLUSDT", "1000LUNCUSDT",
         "VIBUSDT", "WABIUSDT", "WINGSUSDT", "AKROUSDT", "BLZUSDT", "BCPTUSDT",
         "CDTUSDT", "DOCKUSDT", "EVXUSDT", "INSUSDT", "LINAUSDT", "MITHUSDT",
         "MONAUSDT", "NULSUSDT", "PIVXUSDT", "QKCUSDT", "SKILLUSDT", "STMXUSDT",
         "SWRVUSDT", "SYSUSDT", "FIROUSDT", "FISUSDT", "FRONTUSDT", "GASUSDT",
         "PHBUSDT", "REPUSDT", "ZILUSDT", "ARDRUSDT", "SNMUSDT", "BTCSTUSDT"]

BASE = "https://fapi.binance.com/fapi/v1/klines"


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def fetch_1d(sym, start_ms):
    """All daily klines for sym from start_ms (forward pagination)."""
    rows, start = [], start_ms
    while True:
        batch = get(f"{BASE}?symbol={sym}&interval=1d&limit=1000&startTime={start}")
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        start = batch[-1][0] + 1
        if len(rows) > 4000:  # >10y of dailies — safety stop
            break
    # dedupe by open time, sort
    seen, out = set(), []
    for r in sorted(rows, key=lambda x: x[0]):
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return out


# --- probe delisted ----------------------------------------------------------
probe_out = {}
for sym in PROBE:
    p = os.path.join(DAILY, f"{sym}.csv")
    if os.path.exists(p):
        probe_out[sym] = "already-fetched"
        continue
    try:
        rows = fetch_1d(sym, 0)   # full history; listing date from first row
    except Exception as e:
        probe_out[sym] = f"err:{str(e)[:40]}"
        continue
    if rows:
        probe_out[sym] = f"data:{len(rows)}d:first:{rows[0][0]}:last:{rows[-1][0]}"
        with open(p, "w") as f:
            f.write("date,open,high,low,close,volume,quote_volume\n")
            for r in rows:
                f.write(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[7]}\n")
    else:
        probe_out[sym] = "empty"

with open(os.path.join(HERE, "delisted_probe.json"), "w") as f:
    json.dump(probe_out, f, indent=1)

delisted_hits = [s for s, v in probe_out.items() if v.startswith("data:")
                 and s not in active_ids]
print("probe results:", json.dumps(probe_out, indent=0)[:2000])
print("DELISTED-with-data candidates:", delisted_hits)

# --- active 2022+ listings ---------------------------------------------------
targets = [r for r in active if r["onboard_ms"] >= CUTOFF]
print(f"fetching 1d for {len(targets)} active 2022+ listings ...")
fail = []
for i, r in enumerate(sorted(targets, key=lambda x: x["onboard_ms"])):
    sym = r["ccxt_id"]
    p = os.path.join(DAILY, f"{sym}.csv")
    if os.path.exists(p):
        continue
    start = max(r["onboard_ms"] - 3 * 86400000, 0)   # small pre-window
    try:
        rows = fetch_1d(sym, start)
    except Exception as e:
        fail.append((sym, str(e)[:40]))
        continue
    if rows:
        with open(p, "w") as f:
            f.write("date,open,high,low,close,volume,quote_volume\n")
            for k in rows:
                f.write(f"{k[0]},{k[1]},{k[2]},{k[3]},{k[4]},{k[5]},{k[7]}\n")
    if (i + 1) % 50 == 0:
        print(f"  {i + 1}/{len(targets)}")
print("done. failures:", fail)
