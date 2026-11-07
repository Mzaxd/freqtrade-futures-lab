"""LVG evaluation helpers — wallet extraction, anchoring, portfolio synthesis.

Metric definitions (pre_reg.md, CONTEXT §6):
- hourly curves: resample('h').last().ffill()
- portfolio: A/first*7000 + B/first*3000
- daily: resample('D').last(); yearly = groupby(year).last()/first()-1
- dd30: d/d.rolling(30).max()-1, min per year and whole window
- full-window final anchored to start + profit_total_abs (last-candle
  liquidation missing at feather tail)
"""
import io
import json
import zipfile

import numpy as np
import pandas as pd

BASE_A_ZIP = "user_data/backtest_results/backtest-result-2026-11-07_03-54-11.zip"
BASE_B_ZIP = "user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip"


def load_zip(zpath: str):
    """-> (strategy_name, wallet Series hourly-indexed, result dict, anchor_final)"""
    zf = zipfile.ZipFile(zpath)
    jname = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n][0]
    j = json.loads(zf.read(jname))
    sname = list(j["strategy"].keys())[0]
    st = j["strategy"][sname]
    wname = [n for n in zf.namelist() if n.endswith("_wallet.feather")][0]
    w = pd.read_feather(io.BytesIO(zf.read(wname))).set_index("date").sort_index()
    curve = w["total_quote"].resample("h").last().ffill()
    anchor = st["starting_balance"] + st["profit_total_abs"]
    liqs = sum(1 for t in st["trades"] if t.get("is_liquidation"))
    return sname, curve, st, anchor, liqs


def anchor_tail(curve: pd.Series, anchor: float, until: str) -> pd.Series:
    """Scale the final day so the curve ends at `anchor` (last-candle fix).
    Only touches the last calendar day; the last point is forced to anchor
    (linspace with n=1 would return [base] and drop the anchor — bug found
    while auditing baseline A's 2026 figure)."""
    c = curve.copy()
    tail_idx = c.index >= (c.index[-1].floor("D"))
    base = c[~tail_idx].iloc[-1] if (~tail_idx).any() else c.iloc[0]
    day_frac = np.linspace(base, anchor, max(int(tail_idx.sum()), 2))
    c[tail_idx] = day_frac[-int(tail_idx.sum()):]
    c.iloc[-1] = anchor
    return c


def portfolio(a_curve: pd.Series, b_curve: pd.Series, wa=7000, wb=3000) -> pd.Series:
    idx = a_curve.index.union(b_curve.index)
    a = a_curve.reindex(idx).ffill() / a_curve.iloc[0] * wa
    b = b_curve.reindex(idx).ffill() / b_curve.iloc[0] * wb
    return (a.fillna(wa) + b.fillna(wb))


def yearly(dd: pd.Series) -> pd.Series:
    d = dd.resample("D").last()
    g = d.groupby(d.index.year)
    return (g.last() / g.first() - 1) * 100


def dd30(dd: pd.Series) -> pd.Series:
    d = dd.resample("D").last()
    return d / d.rolling(30).max() - 1


def dd30_by_year(dd: pd.Series) -> pd.Series:
    x = dd30(dd) * 100
    g = x.groupby(x.index.year)
    return g.min()


def report(name: str, p: pd.Series) -> str:
    y = yearly(p).round(1).to_dict()
    d30 = (dd30_by_year(p)).round(1).to_dict()
    return f"{name}: yearly={y} dd30min_by_year={d30} dd30min_all={min(dd30_by_year(p).values):.1f}%"
