#!/usr/bin/env python
"""Build bybit leverage-tiers cache for the xexchange whitelist.

freqtrade 2026.8 + ccxt 4.5.64: bybit bulk fetch_leverage_tiers() uses cursor
pagination which intermittently DROPS symbols (observed: 750/765 symbols, our
XRP/USDT:USDT and UNI/USDT:USDT missing -> backtest refuses to run). Per-symbol
fetch_market_leverage_tiers() is reliable. This script builds the standard
freqtrade cache file (user_data/data/bybit/futures/leverage_tiers_USDT.json,
valid for 1 day per freqtrade's bybit.get_leverage_tiers) from the per-symbol
endpoint, so backtesting skips the buggy bulk fetch entirely.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt

REPO = Path(__file__).resolve().parents[3]
PAIRS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
    "LINK/USDT:USDT", "DOT/USDT:USDT", "LTC/USDT:USDT", "UNI/USDT:USDT",
]
OUT = REPO / "user_data" / "data" / "bybit" / "futures" / "leverage_tiers_USDT.json"


def main() -> int:
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    ex.load_markets()
    data = {}
    for pair in PAIRS:
        tiers = ex.fetch_market_leverage_tiers(pair)
        if not tiers:
            print(f"ERROR: empty tiers for {pair}", file=sys.stderr)
            return 1
        data[pair] = tiers
        print(f"{pair}: {len(tiers)} tiers")
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(), "data": data}))
    print(f"cache written: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
