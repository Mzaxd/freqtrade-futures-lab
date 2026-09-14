"""inf_extract_daily.py — build daily equity / return streams from backtest zips.

Outputs under research_deepen/inference/results/:
  daily/<label>_daily.csv   (date, equity, ret)  — calendar-complete, <= 2023-12-31
  trades/<label>_trades.csv (per-trade rows incl. enter_tag, profit_abs, ratio)

Sleeves:
  inf_opt4    : INF_OPT4 zip (frozen OPT4_VolatilitySystem re-run)
  inf_opt2b   : STITCH of the official frozen Sleeve B zips
                (opt2_MomRegime15mLb21_is 2021-22 + _val 2023) in return space;
                sizing is equity-proportional (weights are fractions of
                portfolio value), so a fresh-wallet 2023 has the same %-returns
                as a continuous run — disclosed approximation.
  inf_nfilite : official frozen NFI-Lite zip (opt7_lite_tc3_12p_is)
  combo404020 : 0.4/0.4/0.2 daily-rebalanced mix of the three sleeves above

Daily equity := 10000 + cumulative closed-trade profit_abs, last value per UTC
day. This is exactly the basis of freqtrade's own max_drawdown_account metric
(calculate_max_drawdown runs on the profit_abs cumsum by close_date). The
exported wallet feather is NOT used: under futures/isolated its get_total
includes open-position margin semantics and diverges from final balance by
double-digit % over 3 years (measured 114.2k vs 156.4k for INF_OPT4).

Unrealized MTM swings inside open trades are therefore invisible to this
series — same limitation freqtrade's reported maxDD has. Disclosed in report.
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RES = os.path.join(REPO, "research_deepen", "inference", "results")
BT = os.path.join(REPO, "user_data", "backtest_results")

CUTOFF = pd.Timestamp("2023-12-31", tz="UTC")

SLEEVE_B_IS = os.path.join(BT, "opt2_MomRegime15mLb21_is.zip")
SLEEVE_B_VAL = os.path.join(BT, "opt2_MomRegime15mLb21_val.zip")
NFI_ZIP = os.path.join(BT, "opt7_lite_tc3_12p_is.zip")


def load_zip(zip_path: str) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    """Return (strategy_name, wallet_df, trades_df) from a backtest zip."""
    with zipfile.ZipFile(zip_path) as z:
        jname = [
            n
            for n in z.namelist()
            if n.endswith(".json") and "config" not in n and "market" not in n
        ][0]
        data = json.loads(z.read(jname))
        name, st = next(iter(data["strategy"].items()))
        trades = pd.DataFrame(st["trades"])
        wn = [n for n in z.namelist() if n.endswith("_wallet.feather")]
        if wn:
            wallet = pd.read_feather(io.BytesIO(z.read(wn[0])))
        else:  # fall back to a flat realized-equity curve from trades
            wallet = None
    return name, wallet, trades


def daily_from_trades(trades: pd.DataFrame, start_balance: float = 10000.0) -> pd.Series:
    """Realized equity per UTC day = start_balance + cumsum(profit_abs) by
    close_date, last value per day, calendar-complete (ffill flat days)."""
    t = trades.copy()
    t["close_date"] = pd.to_datetime(t["close_date"], utc=True)
    t = t[t["close_date"].dt.normalize() <= CUTOFF]
    t = t.sort_values("close_date")
    eq = start_balance + t.set_index("close_date")["profit_abs"].cumsum()
    daily = eq.groupby(eq.index.normalize()).last()
    start_day = pd.Timestamp("2021-01-01", tz="UTC")
    daily[start_day] = start_balance  # day 0 anchor before any close
    daily = daily.sort_index()
    full = pd.date_range(start_day, CUTOFF, freq="D", tz="UTC")
    return daily.reindex(full).ffill()


def daily_returns(daily_eq: pd.Series) -> pd.DataFrame:
    daily_eq = daily_eq[daily_eq.index <= CUTOFF]
    ret = daily_eq.pct_change()
    ret.iloc[0] = daily_eq.iloc[0] / 10000.0 - 1.0
    return pd.DataFrame({"equity": daily_eq, "ret": ret})


def save_trades(trades: pd.DataFrame, label: str) -> pd.DataFrame:
    keep = [
        "pair", "is_short", "open_date", "close_date", "enter_tag", "exit_reason",
        "profit_abs", "profit_ratio", "amount", "open_rate", "close_rate",
        "trade_duration",
    ]
    t = trades[[c for c in keep if c in trades.columns]].copy()
    os.makedirs(os.path.join(RES, "trades"), exist_ok=True)
    t.to_csv(os.path.join(RES, "trades", f"{label}_trades.csv"), index=False)
    return t


def main() -> None:
    os.makedirs(os.path.join(RES, "daily"), exist_ok=True)
    streams: dict[str, pd.Series] = {}

    # --- INF_OPT4 (path passed as argv[1]) --------------------------------
    opt4_zip = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RES, "inf_opt4_baseline.zip")
    name, wallet, trades = load_zip(opt4_zip)
    print(f"[opt4] zip strategy={name}, trades={len(trades)}")
    eq = daily_from_trades(trades)
    streams["inf_opt4"] = eq
    save_trades(trades, "inf_opt4")
    r = daily_returns(eq)
    r.to_csv(os.path.join(RES, "daily", "inf_opt4_daily.csv"))

    # --- Sleeve B stitch ----------------------------------------------------
    name_is, w_is, t_is = load_zip(SLEEVE_B_IS)
    name_val, w_val, t_val = load_zip(SLEEVE_B_VAL)
    print(f"[opt2b] is={name_is} ({len(t_is)} trades), val={name_val} ({len(t_val)} trades)")
    eq_is = daily_from_trades(t_is)
    eq_val = daily_from_trades(t_val)
    r_is = daily_returns(eq_is)["ret"]
    r_val = daily_returns(eq_val)["ret"]
    stitched = pd.concat([r_is, r_val])
    stitched = stitched[stitched.index <= CUTOFF].groupby(level=0).sum()
    eqb = 10000.0 * (1.0 + stitched).cumprod()
    streams["inf_opt2b"] = eqb
    save_trades(pd.concat([t_is, t_val]), "inf_opt2b")
    pd.DataFrame({"equity": eqb, "ret": stitched}).to_csv(
        os.path.join(RES, "daily", "inf_opt2b_daily.csv")
    )

    # --- NFI-Lite -----------------------------------------------------------
    name_n, w_n, t_n = load_zip(NFI_ZIP)
    print(f"[nfilite] zip strategy={name_n}, trades={len(t_n)}")
    eqn = daily_from_trades(t_n)
    streams["inf_nfilite"] = eqn
    save_trades(t_n, "inf_nfilite")
    pd.DataFrame(daily_returns(eqn)).to_csv(os.path.join(RES, "daily", "inf_nfilite_daily.csv"))

    # --- 40/40/20 daily-rebalanced combo -----------------------------------
    rets = pd.DataFrame({k: daily_returns(v)["ret"] for k, v in streams.items()})
    rets = rets.fillna(0.0)
    combo = 0.4 * rets["inf_opt4"] + 0.4 * rets["inf_opt2b"] + 0.2 * rets["inf_nfilite"]
    eqc = 10000.0 * (1.0 + combo).cumprod()
    pd.DataFrame({"equity": eqc, "ret": combo}).to_csv(
        os.path.join(RES, "daily", "combo404020_daily.csv")
    )

    # --- summary -------------------------------------------------------------
    print("\n=== daily stream summary (realized-equity basis, <= 2023-12-31) ===")
    for label, series in {
        "inf_opt4": eq,
        "inf_opt2b": eqb,
        "inf_nfilite": eqn,
        "combo404020": eqc,
    }.items():
        series = series[series.index <= CUTOFF]
        r = series.pct_change().dropna()
        total = series.iloc[-1] / series.iloc[0] - 1
        peak = series.cummax()
        dd = series / peak - 1.0
        print(
            f"{label:12s} days={len(series):4d} total={total * 100:9.1f}% "
            f"maxDD={dd.min() * 100:6.2f}% "
            f"ann.Sharpe={(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else float('nan'):.3f} "
            f"final_eq={series.iloc[-1]:.0f}"
        )


if __name__ == "__main__":
    main()
