"""uni/step1 — enumerate active Binance USDT-M COIN perps listed >= 2022-01-01.

Uses ccxt market metadata only (underlyingType==COIN, underlyingSubType has
'Crypto', onboardDate). Writes research_improve/uni/active_meta.json.
Also probes Binance Vision S3 bucket for ALL symbols that ever had um kline
dumps (active ∪ delisted) -> research_improve/uni/vision_symbols.json.
"""
import json
import os
import urllib.request

import ccxt

HERE = os.path.dirname(os.path.abspath(__file__))

ex = ccxt.binanceusdm({"enableRateLimit": True, "timeout": 30000})
markets = ex.load_markets()

rows = []
for sym, m in markets.items():
    if not sym.endswith("/USDT:USDT"):
        continue
    info = m.get("info", {})
    if info.get("underlyingType") != "COIN":
        continue
    sub = info.get("underlyingSubType") or []
    if "Crypto" not in sub and "DeFi" not in sub:
        continue
    onboard = int(info.get("onboardDate", 0))
    rows.append({
        "symbol": sym,                     # e.g. RAYSOL/USDT:USDT
        "ccxt_id": m["id"],                # e.g. RAYSOLUSDT
        "onboard_ms": onboard,
        "status": info.get("status"),
    })

with open(os.path.join(HERE, "active_meta.json"), "w") as f:
    json.dump(rows, f, indent=1)

cutoff = 1640995200000  # 2022-01-01 UTC
new = [r for r in rows if r["onboard_ms"] >= cutoff]
print(f"active COIN+Crypto USDT perps total={len(rows)}  listed>=2022-01-01={len(new)}")

# --- Binance Vision: all symbols that ever had um monthly klines -------------
def s3_list(prefix):
    """Paginate the dataset.binance.vision S3 bucket for common-prefixes."""
    out, token = [], None
    while True:
        url = ("https://s3-ap-northeast-1.amazonaws.com/dataset.binance.vision"
               f"?delimiter=/&max-keys=1000&prefix={prefix}")
        if token:
            url += f"&marker={token}"
        with urllib.request.urlopen(url, timeout=60) as r:
            text = r.read().decode()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
        ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
        prefixes = [e.findtext(ns + "Prefix") for e in root.findall(ns + "CommonPrefixes")]
        out.extend(prefixes)
        tok = root.findtext(ns + "NextMarker")
        if not tok:
            break
        token = tok
    return out


try:
    syms = s3_list("data/futures/um/monthly/klines/")
    vis = sorted(p.split("/")[4] for p in syms if len(p.split("/")) > 4)
    with open(os.path.join(HERE, "vision_symbols.json"), "w") as f:
        json.dump(vis, f, indent=0)
    print(f"vision um-kline symbols (incl. delisted): {len(vis)}")
except Exception as e:
    print("vision listing FAILED:", e)
