# -*- coding: utf-8 -*-
"""阶段 B（PREREG v2）：按 2021-01-01→2023-12-31 窗口 1d 名义成交额中位数对候选排序，冻结 top-40。
输出: universe_frozen_v2.json / universe_frozen_v2.md
"""
import json
import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
DATADIR = HERE / "userdir" / "data" / "binance" / "futures"


def main():
    cands = json.load(open(HERE / "candidates.json", encoding="utf-8"))["candidates"]
    rows = []
    for c in cands:
        base = c["symbol"].split("/")[0]
        f = DATADIR / f"{base}_USDT_USDT-1d-futures.feather"
        if not f.exists():
            rows.append({"symbol": c["symbol"], "notional_median": None,
                         "days_in_window": 0, "note": "download missing"})
            continue
        df = pd.read_feather(f).set_index("date")
        win = df[(df.index >= pd.Timestamp("2021-01-01", tz="UTC")) &
                 (df.index < pd.Timestamp("2024-01-01", tz="UTC"))]
        if len(win) == 0:
            rows.append({"symbol": c["symbol"], "notional_median": None,
                         "days_in_window": 0, "note": "no data in window"})
            continue
        notional = (win["close"] * win["volume"]).median()
        rows.append({"symbol": c["symbol"], "notional_median": float(notional),
                     "days_in_window": int(len(win)), "note": ""})
    rows.sort(key=lambda r: (r["notional_median"] is not None,
                             r["notional_median"] or 0), reverse=True)
    top40 = [r for r in rows[:40] if r["notional_median"] is not None]
    out = {
        "selection_date_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "rule": "median daily close*volume (USDT notional) over 2021-01-01..2023-12-31, "
                "among active linear USDT perps listed (1d first candle) <= 2021-12-31, non-stable base",
        "n_candidates": len(rows),
        "top40": top40,
        "rejected_ranks_41_onward": rows[40:],
    }
    (HERE / "universe_frozen_v2.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# 冻结宇宙 v2（研究窗口流动性 top-40）", "",
        f"- 冻结时间(UTC): {out['selection_date_utc']}",
        f"- 规则: {out['rule']}", "",
        "| rank | symbol | 窗口内名义成交额中位数(USDT/日) | 窗口内天数 |",
        "|---:|:---|---:|---:|",
    ]
    for i, r in enumerate(top40, 1):
        lines.append(f"| {i} | {r['symbol']} | {r['notional_median']:,.0f} | {r['days_in_window']} |")
    (HERE / "universe_frozen_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("frozen v2 top40:", [r["symbol"] for r in top40])
    missing = [r for r in rows if r["notional_median"] is None]
    if missing:
        print("missing-data candidates (not eligible):", [r["symbol"] for r in missing])


if __name__ == "__main__":
    main()
