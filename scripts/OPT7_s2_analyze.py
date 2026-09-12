#!/usr/bin/env python3
"""OPT7_s2_analyze — Phase 7 / S2 analysis utilities for OversoldReversion deepening.

Usage (all outputs to stdout):
  summarize <zip> [strategy_key]        — trade/PF/DD/funding/exit-reason summary
  monthly <zip> [strategy_key]          — month-end equity + monthly returns table
  corr <zipA> <keyA> <zipB> <keyB> ...  — Pearson corr of monthly returns across >=2 zips
"""
from __future__ import annotations

import json
import sys
import zipfile

import pandas as pd


def load_strategy(zip_path: str, key: str | None = None) -> tuple[str, dict]:
    zf = zipfile.ZipFile(zip_path)
    name = [n for n in zf.namelist()
            if n.endswith(".json") and "config" not in n and "market" not in n][0]
    d = json.loads(zf.read(name))
    strategies = d["strategy"]
    if key is None:
        key = list(strategies)[0]
    return key, strategies[key]


def summarize(zip_path: str, key: str | None = None) -> None:
    key, s = load_strategy(zip_path, key)
    trades = pd.DataFrame(s["trades"])
    n = len(trades)
    profit = trades["profit_abs"].sum()
    wins = trades[trades["profit_abs"] > 0]
    losses = trades[trades["profit_abs"] <= 0]
    gross_w = wins["profit_abs"].sum()
    gross_l = -losses["profit_abs"].sum()
    pf = gross_w / gross_l if gross_l > 0 else float("inf")
    funding = trades["funding_fees"].sum()
    funding_recv = trades.loc[trades["funding_fees"] > 0, "funding_fees"].sum()
    funding_paid = trades.loc[trades["funding_fees"] < 0, "funding_fees"].sum()
    print(f"== {zip_path.split('/')[-1]} [{key}]")
    print(f"trades={n}  profit_abs={profit:,.1f}  profit%={s.get('profit_total')*100 if s.get('profit_total') is not None else float('nan'):.2f}%"
          f"  PF(zip)={s.get('profit_factor'):.3f}  PF(calc)={pf:.3f}")
    print(f"win_rate={len(wins)/n*100 if n else 0:.1f}%  maxDD_account={s.get('max_drawdown_account')*100:.2f}%"
          f"  sharpe={s.get('sharpe')}")
    print(f"funding: net={funding:,.1f}  received={funding_recv:,.1f}  paid={funding_paid:,.1f}"
          f"  | net funding / profit_abs = {funding/profit*100 if profit else 0:.1f}%")
    trades["year"] = pd.to_datetime(trades["close_date"]).dt.year
    for y, g in trades.groupby("year"):
        gw = g.loc[g.profit_abs > 0, "profit_abs"].sum()
        gl = -g.loc[g.profit_abs <= 0, "profit_abs"].sum()
        print(f"  {y}: n={len(g):3d}  PnL={g['profit_abs'].sum():9,.1f}  funding={g['funding_fees'].sum():8,.1f}"
              f"  PF={gw/gl if gl>0 else float('inf'):.2f}")
    print("exit_reasons:", dict(trades["exit_reason"].value_counts()))
    print("per_pair:")
    for p, g in trades.groupby("pair"):
        print(f"  {p:16s} n={len(g):3d}  PnL={g['profit_abs'].sum():9,.1f}  funding={g['funding_fees'].sum():8,.1f}")


def monthly_series(zip_path: str, key: str | None = None) -> pd.Series:
    """Monthly returns reconstructed per the phase-6 v2 approximation:
    equity = 10000 + cumsum(profit_abs) at trade close times; monthly return =
    month-end equity / prior month-end equity - 1. Disclosed approximation."""
    key, s = load_strategy(zip_path, key)
    trades = pd.DataFrame(s["trades"])
    trades["close_dt"] = pd.to_datetime(trades["close_date"])
    trades = trades.sort_values("close_dt")
    eq = 10000.0 + trades["profit_abs"].cumsum()
    ser = pd.Series(eq.values, index=trades["close_dt"].values)
    pts = pd.concat([pd.Series([10000.0], index=[pd.Timestamp(s["backtest_start"])]), ser])
    # anchor at window end so silent tail months show as flat equity (true 0% months)
    pts = pd.concat([pts, pd.Series([pts.iloc[-1]], index=[pd.Timestamp(s["backtest_end"])])])
    month_end = pts.resample("ME").last().ffill()
    return month_end.pct_change().dropna()


def cmd_monthly(zip_path: str, key: str | None = None) -> None:
    rets = monthly_series(zip_path, key)
    for m, r in rets.items():
        print(f"{m.strftime('%Y-%m')}  {r*100:8.2f}%")
    print(f"n_months={len(rets)}  sum={rets.sum()*100:.2f}%  pos_months={(rets>0).sum()}")


def cmd_corr(args: list[str]) -> None:
    assert len(args) >= 4 and len(args) % 2 == 0
    series = []
    labels = []
    for i in range(0, len(args), 2):
        zp, k = args[i], (args[i + 1] if args[i + 1] != "-" else None)
        series.append(monthly_series(zp, k))
        labels.append(zp.split("/")[-1].replace(".zip", "") + (f"[{k}]" if k else ""))
    df = pd.concat(series, axis=1, keys=labels)
    df = df.dropna()
    print("common months:", f"{df.index.min().strftime('%Y-%m')}..{df.index.max().strftime('%Y-%m')} n={len(df)}")
    print(df.corr(min_periods=6).round(4).to_string())


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "summarize":
        summarize(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "monthly":
        cmd_monthly(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "corr":
        cmd_corr(sys.argv[2:])
    else:
        raise SystemExit(__doc__)
