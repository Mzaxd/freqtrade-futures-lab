"""CRASH shared library: wallet-curve extraction from backtest zips + IS baseline stats.

Standard method per CONTEXT §6:
  zip -> <Strategy>_wallet.feather (date/total_quote) -> daily curve.
  Final-value anchoring uses strategy.<name>.profit_total_abs from the result JSON
  (only matters at the run tail; interior slicing is unaffected).

Usage (module): import and call load_wallet(zip_path, strategy_class_name).
CLI: IS baseline stats for the A sleeve (cut at 2024-01-01): yearly returns,
     DD-episode anatomy below 0.92x running peak, slice DDs.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

LAB = Path(__file__).resolve().parents[2]


def load_wallet(zip_path: Path | str, strategy: str) -> pd.Series:
    """Daily (hourly-resolution) total_quote wallet curve for one strategy run."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        wname = [n for n in names if n.endswith("_wallet.feather") and strategy in n.split("_")[0]]
        # wallet feather is named "<Strategy>_wallet.feather"; match exactly
        cand = [n for n in names if n == f"{strategy}_wallet.feather"]
        if not cand:
            cand = [n for n in names if n.endswith(".feather") and strategy in n]
        if not cand:
            raise FileNotFoundError(f"no wallet feather for {strategy} in {zip_path}: {names}")
        raw = z.read(cand[0])
    df = pd.read_feather(io.BytesIO(raw))
    df["date"] = pd.to_datetime(df["date"], utc=True)
    s = df.set_index("date")["total_quote"].astype(float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def anchor_final(zip_path: Path | str, strategy: str) -> tuple[float, float]:
    """(start_wallet, final_balance) from the result JSON inside the zip."""
    with zipfile.ZipFile(zip_path) as z:
        jname = [n for n in z.namelist() if n.endswith(".json") and "config" not in n][0]
        meta = json.loads(z.read(jname).decode())
    res = meta["strategy"][strategy]
    return float(res["starting_balance"]), float(res["starting_balance"] + res["profit_total_abs"])


def yearly_returns(hourly: pd.Series) -> dict[int, float]:
    d = hourly.resample("D").last().dropna()
    out = {}
    for y, g in d.groupby(d.index.year):
        out[int(y)] = float(g.iloc[-1] / g.iloc[0] - 1.0)
    return out


def dd_from_peak(hourly: pd.Series) -> pd.Series:
    d = hourly.resample("D").last().dropna()
    return d / d.cummax() - 1.0


def dd30_rolling(hourly: pd.Series) -> pd.Series:
    d = hourly.resample("D").last().dropna()
    return d / d.rolling(30).max() - 1.0


def dd_episode_anatomy(hourly: pd.Series, arm: float = 0.92) -> dict:
    """Days below arm x running peak; episode count / durations (IS planning only)."""
    d = hourly.resample("D").last().dropna()
    below = d < arm * d.cummax()
    episodes = (below.astype(int).diff().clip(lower=0) == 1).sum()
    runs = below.astype(int)
    # longest run
    max_run = cur = 0
    for v in runs:
        cur = cur + 1 if v else 0
        max_run = max(max_run, cur)
    return {
        "days_below_arm": int(below.sum()),
        "total_days": int(len(d)),
        "frac_below": round(float(below.mean()), 3),
        "episodes": int(episodes),
        "longest_run_days": int(max_run),
    }


if __name__ == "__main__":
    strat = sys.argv[1] if len(sys.argv) > 1 else "ARL_2x"
    zp = LAB / "user_data" / "backtest_results" / "backtest-result-2026-11-07_03-54-11.zip"
    w = load_wallet(zp, strat)
    is_cut = pd.Timestamp("2024-01-01", tz="UTC")
    w_is = w[w.index < is_cut]
    print(f"{strat} IS curve: {w_is.index[0]} .. {w_is.index[-1]}, {len(w_is)} rows")
    print("yearly (IS, unanchored interior):", yearly_returns(w_is))
    print("dd episodes <0.92x peak:", dd_episode_anatomy(w_is))
    dd = dd_from_peak(w_is)
    print("max from-peak DD IS:", round(float(dd.min()), 4))
    sl = w_is[w_is.index >= pd.Timestamp("2022-05-01", tz="UTC")]
    sl = sl[sl.index < pd.Timestamp("2023-01-01", tz="UTC")]
    ddsl = sl / sl.cummax() - 1.0
    print("2022-05..12 slice: return", round(float(sl.iloc[-1] / sl.iloc[0] - 1), 4),
          "from-peak DD", round(float(ddsl.min()), 4))
