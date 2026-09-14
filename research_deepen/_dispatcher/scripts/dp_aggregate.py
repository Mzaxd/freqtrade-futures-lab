# dp_aggregate.py — 3-sleeve portfolio aggregation for the 24-26 disclosed
# diagnostic + 21-26 stitched view. Convention mirrors PRT prt07 exactly:
# daily-rebalanced fixed weights, r_p(t) = sum_i w_i * r_i(t).
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
PRT_RES = os.path.join(ROOT, "research_deepen", "portfolio", "results")
DP_RES = os.path.join(ROOT, "research_deepen", "_dispatcher", "results")


def metrics(ret: np.ndarray, days_per_year=365.0):
    eq = np.cumprod(1 + ret)
    yrs = len(ret) / days_per_year
    total = eq[-1] - 1
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(days_per_year)
    sharpe = ret.mean() * days_per_year / vol if vol > 0 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak - 1).min()
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    return total, cagr, vol, sharpe, dd, calmar


def load_sleeves():
    # Stitch RETURNS, not equity levels: each window's backtest restarts at
    # INIT=10k, so concatenating levels would inject a fake boundary jump.
    rets = {}
    for tag in ("A", "B", "N"):
        p23 = pd.read_csv(os.path.join(PRT_RES, f"mtm_daily_{tag}.csv"),
                          index_col=0, parse_dates=True).iloc[:, 0]
        p24 = pd.read_csv(os.path.join(DP_RES, f"mtm_daily_{tag}_2426.csv"),
                          index_col=0, parse_dates=True).iloc[:, 0]
        p24 = p24[~p24.index.isin(p23.index)]  # drop boundary overlap day if any
        rets[tag] = pd.concat([p23.pct_change(), p24.pct_change()]).dropna().sort_index()
    daily = pd.DataFrame(rets)
    return daily, daily


def seg(rets, start, end):
    return rets[(rets.index >= start) & (rets.index <= end)]


def row(name, ret, weights=None):
    if weights is not None:
        ret = ret.to_numpy(float) @ np.array(weights)
    t, c, v, s, dd, ca = metrics(ret)
    return dict(seg=name, total=round(t, 4), cagr=round(c, 4), annvol=round(v, 4),
                sharpe=round(s, 3), maxdd=round(dd, 4), calmar=round(ca, 3))


def main():
    daily, rets = load_sleeves()
    print("sleeve daily-return coverage:")
    print(rets.describe().loc[["count", "mean", "max"]].to_string())

    W = {"45/25/30": (0.45, 0.25, 0.30), "40/40/20": (0.40, 0.40, 0.20)}
    rows = []
    # 21-23 sanity (should reproduce PRT mtm numbers)
    for wn, w in W.items():
        rows.append(row(f"21-23 {wn}", seg(rets, "2021-01-01", "2023-12-31"), w))
    # 24-26 diagnostic segments
    for tag, w in [("A only", (1, 0, 0)), ("B only", (0, 1, 0)), ("N only", (0, 0, 1))] + list(W.items()):
        rows.append(row(f"24-26 {tag}", seg(rets, "2024-01-01", "2026-12-31"), w))
    # stitched 21-26 (boundary disclosed)
    for wn, w in W.items():
        rows.append(row(f"21-26 {wn} (stitched)", rets, w))

    df = pd.DataFrame(rows)
    out = os.path.join(DP_RES, "dp_aggregate.csv")
    df.to_csv(out, index=False)
    print(df.to_string(index=False))
    print("wrote", out)

    # yearly breakdown of the recommended portfolio
    r452530 = rets.to_numpy(float) @ np.array(W["45/25/30"])
    yearly = pd.Series(1 + r452530, index=rets.index).groupby(rets.index.year).prod() - 1
    print("\n45/25/30 yearly returns:")
    print((yearly * 100).round(1).to_string())
    dd_series = (pd.Series(1 + r452530, index=rets.index).cumprod()
                 / pd.Series(1 + r452530, index=rets.index).cumprod().cummax() - 1)
    worst = dd_series.nsmallest(5)
    print("\n45/25/30 worst drawdown dates:")
    print((worst * 100).round(1).to_string())


if __name__ == "__main__":
    main()
