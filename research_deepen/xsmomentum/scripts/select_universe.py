# -*- coding: utf-8 -*-
"""按 PREREGISTRATION.md 第 1 节规则生成 Binance USDT-M 永续流动性 top-40 宇宙并冻结名单。
输出: research_deepen/xsmomentum/universe_frozen.json + universe_frozen.md
"""
import json
import sys
import datetime
from pathlib import Path
import ccxt

STABLE_LIKE = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "USDD", "FRAX", "EUR",
    "GBP", "AUD", "BRL", "TRY", "EURI", "XUSD", "PAXG", "USDE", "USD1",
    "AEUR", "PYUSD", "EURC", "USDCEUR", "BFUSD", "USTC", "UST",
}

def main():
    ex = ccxt.binanceusdm()
    ex.load_markets()
    tickers = ex.fetch_tickers()
    rows = []
    for sym, t in tickers.items():
        m = ex.markets.get(sym)
        if m is None:
            continue
        if not (m.get("swap") and m.get("linear") and m.get("quote") == "USDT"):
            continue
        if not m.get("active", True):
            continue
        base = m.get("base", "")
        if base in STABLE_LIKE:
            continue
        qv = t.get("quoteVolume") or 0
        rows.append({"symbol": sym, "base": base, "quote_volume_24h": float(qv)})

    rows.sort(key=lambda r: r["quote_volume_24h"], reverse=True)
    top40 = rows[:40]

    out = {
        "selection_date_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "exchange": "binanceusdm (Binance USDT-M perpetual, linear swaps)",
        "ranking_metric": "24h quoteVolume (USDT) from ccxt fetch_tickers snapshot",
        "filters": "linear USDT perpetual, active, base not stable/fiat-pegged",
        "top40": top40,
        "next_10_for_disclosure": [
            {"symbol": r["symbol"], "quote_volume_24h": r["quote_volume_24h"]}
            for r in rows[40:50]
        ],
    }
    Path("universe_frozen.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# 冻结宇宙（Binance USDT-M 永续 24h quote volume top-40）",
        "",
        f"- 选择时间(UTC): {out['selection_date_utc']}",
        f"- 排序依据: {out['ranking_metric']}",
        "",
        "| rank | symbol | 24h quoteVolume(USDT) |",
        "|---:|:---|---:|",
    ]
    for i, r in enumerate(top40, 1):
        lines.append(f"| {i} | {r['symbol']} | {r['quote_volume_24h']:,.0f} |")
    lines += ["", "## 落选边缘（第 41-50 名，仅披露，不入选）", "",
              "| rank | symbol | 24h quoteVolume(USDT) |", "|---:|:---|---:|"]
    for j, r in enumerate(out["next_10_for_disclosure"], 41):
        lines.append(f"| {j} | {r['symbol']} | {r['quote_volume_24h']:,.0f} |")
    Path("universe_frozen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("frozen top40:", [r["symbol"] for r in top40])

if __name__ == "__main__":
    sys.exit(main())
