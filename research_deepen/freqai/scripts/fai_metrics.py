#!/usr/bin/env python
"""FAI metrics: slice a fai_*.zip backtest result into 2021-22 (dev) and 2023 (VAL-like)
segments; compute the pre-registered kill criteria per segment (K1..K5).

Usage: python fai_metrics.py <zip> [<zip2> ...]
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SEGMENTS = {
    "2021-22": ("2021-01-01", "2023-01-01"),
    "2023": ("2023-01-01", "2024-01-01"),
    "2021": ("2021-01-01", "2022-01-01"),
    "2022": ("2022-01-01", "2023-01-01"),
}


def load_trades(zippath: str) -> tuple[str, pd.DataFrame, float, float]:
    z = zipfile.ZipFile(zippath)
    jname = [n for n in z.namelist() if n.endswith(".json") and "config" not in n and "market" not in n][0]
    data = json.loads(z.read(jname))
    strat = list(data["strategy"].keys())[0]
    st = data["strategy"][strat]
    tr = pd.DataFrame(st["trades"])
    if tr.empty:
        return strat, tr, 0.0, 0.0
    tr["open_date"] = pd.to_datetime(tr["open_date"], utc=True)
    tr["close_date"] = pd.to_datetime(tr["close_date"], utc=True)
    start_bal = data["strategy"][strat]["starting_balance"]
    return strat, tr, start_bal, st["profit_total"]


def seg_stats(tr: pd.DataFrame, start_bal: float) -> dict:
    if tr.empty:
        return {"trades": 0}
    gross_win = tr.loc[tr["profit_abs"] > 0, "profit_abs"].sum()
    gross_loss = -tr.loc[tr["profit_abs"] < 0, "profit_abs"].sum()
    n = len(tr)
    return {
        "trades": n,
        "profit_abs": round(tr["profit_abs"].sum(), 1),
        "profit_pct_vs_10k": round(tr["profit_abs"].sum() / start_bal * 100, 2),
        "PF": round(gross_win / gross_loss, 3) if gross_loss > 0 else float("inf"),
        "avg_profit_pct": round(tr["profit_ratio"].mean() * 100, 4),
        "med_profit_pct": round(tr["profit_ratio"].median() * 100, 4),
        "winrate": round((tr["profit_ratio"] > 0).mean(), 4),
        "n_short": int(tr["is_short"].sum()),
        "n_long": n - int(tr["is_short"].sum()),
        "avg_hold_h": round((tr["close_date"] - tr["open_date"]).dt.total_seconds().mean() / 3600, 1),
        "fee_abs": round(tr["fee_abs"].sum() if "fee_abs" in tr else 0, 1),
    }


def exit_breakdown(tr: pd.DataFrame) -> str:
    if tr.empty:
        return "(no trades)"
    g = tr.groupby("exit_reason").agg(n=("profit_ratio", "size"),
                                      mean_pct=("profit_ratio", lambda s: round(s.mean() * 100, 3)))
    return g.to_dict("index")


def main(zips: list[str]) -> None:
    for zp in zips:
        strat, tr, bal, total = load_trades(zp)
        thr = zp.split("_t")[-1].replace(".zip", "")
        print(f"\n===== {Path(zp).name} (strategy {strat}, threshold {thr}) =====")
        print(f"full-run profit_total: {total * 100:.2f}%  starting_balance {bal}")
        for name, (lo, hi) in SEGMENTS.items():
            m = (tr["open_date"] >= pd.Timestamp(lo, tz="UTC")) & (tr["open_date"] < pd.Timestamp(hi, tz="UTC"))
            s = seg_stats(tr[m], bal)
            print(f"[{name}] {s}")
        print("exits:", exit_breakdown(tr))


if __name__ == "__main__":
    main(sys.argv[1:])
