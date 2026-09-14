# -*- coding: utf-8 -*-
"""阶段 A（PREREG v2）：候选集 = 当前仍上市的线性 USDT 永续，非稳定基币，
首根 1d K 线(onboardDate) <= 2021-12-31。输出 candidates.json。
"""
import json
import datetime
from pathlib import Path
import ccxt

STABLE_LIKE = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "USDD", "FRAX", "EUR",
    "GBP", "AUD", "BRL", "TRY", "EURI", "XUSD", "PAXG", "USDE", "USD1",
    "AEUR", "PYUSD", "EURC", "BFUSD", "USTC", "UST",
}

def main():
    ex = ccxt.binanceusdm()
    ex.load_markets()
    cutoff = datetime.datetime(2021, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)
    out = []
    for sym, m in ex.markets.items():
        if not (m.get("swap") and m.get("linear") and m.get("quote") == "USDT"):
            continue
        if not m.get("active", True):
            continue
        base = m.get("base", "")
        if base in STABLE_LIKE:
            continue
        info = m.get("info", {})
        obd = info.get("onboardDate")
        if obd is None:
            continue
        dt = datetime.datetime.fromtimestamp(int(obd) / 1000, tz=datetime.timezone.utc)
        if dt > cutoff:
            continue
        out.append({"symbol": sym, "base": base, "onboardDate": dt.isoformat()})
    out.sort(key=lambda r: r["symbol"])
    Path("candidates.json").write_text(json.dumps(
        {"generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "cutoff_rule": "onboardDate <= 2021-12-31, active linear USDT perp, non-stable base",
         "count": len(out), "candidates": out}, indent=2), encoding="utf-8")
    print("candidates:", len(out))

if __name__ == "__main__":
    main()
