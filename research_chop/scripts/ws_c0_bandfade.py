"""WS-C0 deliverable 3: naive band-fade theoretical ceiling (NOT a strategy).

Pre-registered rule (PRE_REGISTRATION.md / WS-C0 brief), implemented causally:
- Bollinger(96h, 2.0 sigma, population std ddof=0) on 1h close.
- Entry signal at bar t CLOSE: close beyond band AND gate label ON at t
  (label at t is computed from <=t data; it authorizes execution at t+1 open).
  Long below lower band / short above upper band. Execution at open[t+1].
- Exit: close back at/through the mid band (close>=sma for long) evaluated at
  bar close -> exit at next bar open; OR forced liquidation at open of bar
  entry_bar+48 (exactly 48 h after entry). Gate OFF does NOT force exit
  (interpretation of "only trade during ON hours" = entry gating; disclosed).
- One position at a time; notional per trade = 1 x current equity (fixed unit);
  fees 0.0005 per side; no slippage, no funding (optimistic, disclosed).
- Hourly marked-to-market equity -> max drawdown. Open position at window end
  is force-closed at the last close (truncation disclosed).
- IS = 2021-01-01..2023-12-31, OS = 2024-01-01..2026-09-12, fresh equity 10000.

Outputs (research_chop/logs/):
  ws_c0_bandfade_results.csv  summary per window x coin x gate
  ws_c0_bandfade_trades_{COIN}_{gate}_{win}.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEATHER = ROOT / "user_data" / "data" / "binance" / "futures"
DATA = ROOT / "research_chop" / "data"
LOGS = ROOT / "research_chop" / "logs"
COINS = ["BTC", "ETH", "SOL"]
GATES = ["g2", "g4"]
WINDOWS = {"IS": ("2021-01-01 00:00+00:00", "2023-12-31 23:00+00:00"),
           "OS": ("2024-01-01 00:00+00:00", "2026-09-12 23:00+00:00")}
BB_N, BB_K = 96, 2.0
FEE = 0.0005
MAX_HOLD = 48
EQ0 = 10000.0


def run(df: pd.DataFrame, gate_col: str, win: str) -> tuple[dict, pd.DataFrame]:
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()
    sma = df["close"].rolling(BB_N).mean()
    sd = df["close"].rolling(BB_N, min_periods=BB_N).std(ddof=0)
    lower = (sma - BB_K * sd).to_numpy()
    upper = (sma + BB_K * sd).to_numpy()
    sma = sma.to_numpy()
    g = df[gate_col].to_numpy(dtype=bool)

    w0, w1 = WINDOWS[win]
    n = len(df)
    idx0 = int(df.index.get_indexer([pd.Timestamp(w0)], method="bfill")[0])
    idx1 = int(df.index.get_indexer([pd.Timestamp(w1)], method="ffill")[0])
    eq, pos, entry_px, entry_i, eq_entry = EQ0, 0, np.nan, -1, EQ0
    eq_curve = np.full(n, np.nan)
    trades = []
    n_breach = n_breach_on = 0

    for i in range(max(idx0, 1), idx1 + 1):
        # ---- exits first (executed at open[i]) ----
        if pos != 0:
            mid_sig = (pos > 0 and c[i - 1] >= sma[i - 1]) or (pos < 0 and c[i - 1] <= sma[i - 1])
            force = (i - entry_i) >= MAX_HOLD
            if mid_sig or force:
                px = o[i]
                eq = eq_entry * (1 + pos * (px / entry_px - 1)) * (1 - FEE)
                trades.append({
                    "dir": "long" if pos > 0 else "short",
                    "entry_time": df.index[entry_i], "exit_time": df.index[i],
                    "hold_h": i - entry_i,
                    "net_pct": round(100 * (pos * (px / entry_px - 1) - 2 * FEE), 4),
                    "exit_reason": "midband" if mid_sig else "force48h"})
                pos = 0
        # ---- entry (signal at bar i-1 close, execution at open[i]) ----
        if pos == 0:
            breach_dn = c[i - 1] < lower[i - 1]
            breach_up = c[i - 1] > upper[i - 1]
            if breach_dn or breach_up:
                n_breach += 1
            if g[i - 1]:
                if breach_dn or breach_up:
                    n_breach_on += 1
                if breach_dn:
                    pos, entry_px, entry_i = 1, o[i], i
                    eq_entry = eq * (1 - FEE)
                elif breach_up:
                    pos, entry_px, entry_i = -1, o[i], i
                    eq_entry = eq * (1 - FEE)
        # ---- hourly mark ----
        if pos != 0:
            eq_curve[i] = eq_entry * (1 + pos * (c[i] / entry_px - 1))
        else:
            eq_curve[i] = eq

    # ---- window-end truncation: force close at last close ----
    truncated = pos != 0
    if truncated:
        px = c[idx1]
        eq = eq_entry * (1 + pos * (px / entry_px - 1)) * (1 - FEE)
        trades.append({
            "dir": "long" if pos > 0 else "short",
            "entry_time": df.index[entry_i], "exit_time": df.index[idx1],
            "hold_h": idx1 - entry_i,
            "net_pct": round(100 * (pos * (px / entry_px - 1) - 2 * FEE), 4),
            "exit_reason": "window_end"})
        eq_curve[idx1] = eq

    curve = pd.Series(eq_curve[idx0:idx1 + 1], index=df.index[idx0:idx1 + 1]).ffill()
    dd = (curve / curve.cummax() - 1).min()
    tdf = pd.DataFrame(trades)
    stats = {
        "win": win, "coin": df.attrs["coin"], "gate": gate_col,
        "n_trades": len(tdf),
        "win_rate_pct": round(100 * (tdf["net_pct"] > 0).mean(), 1) if len(tdf) else np.nan,
        "avg_net_per_trade_pct": round(tdf["net_pct"].mean(), 3) if len(tdf) else np.nan,
        "cum_net_ret_pct": round(100 * (eq / EQ0 - 1), 2),
        "mdd_pct": round(100 * dd, 2),
        "avg_hold_h": round(tdf["hold_h"].mean(), 1) if len(tdf) else np.nan,
        "breach_hours_total": n_breach, "breach_hours_gate_on": n_breach_on,
        "open_truncation": truncated}
    return stats, tdf


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    import os
    # DIAG=1 adds an ungated pseudo-gate (every hour ON) as a *diagnostic
    # context only* -- NOT part of the pre-registered deliverable table.
    diag = os.environ.get("DIAG") == "1"
    gates = GATES + ["g_all"] if diag else GATES
    all_stats = []
    for coin in COINS:
        pair = f"{coin}_USDT_USDT"
        px = pd.read_feather(FEATHER / f"{pair}-1h-futures.feather").set_index("date")
        lab = pd.read_csv(DATA / f"regime_1h_{coin}.csv", parse_dates=["date"]).set_index("date")
        df = px.join(lab[GATES], how="left")
        if diag:
            df["g_all"] = True
        df.attrs["coin"] = coin
        for gate in gates:
            for win in WINDOWS:
                stats, tdf = run(df, gate, win)
                all_stats.append(stats)
                tdf.to_csv(LOGS / f"ws_c0_bandfade_trades_{coin}_{gate}_{win}.csv", index=False)
                print(f"{coin} {gate} {win}: n={stats['n_trades']:4d} "
                      f"wr={stats['win_rate_pct']}% avg={stats['avg_net_per_trade_pct']}% "
                      f"cum={stats['cum_net_ret_pct']}% mdd={stats['mdd_pct']}% "
                      f"breach_on/total={stats['breach_hours_gate_on']}/{stats['breach_hours_total']}")
    out = pd.DataFrame(all_stats)
    out.to_csv(LOGS / "ws_c0_bandfade_results.csv", index=False)
    print("\n== equal-weight 3-coin average of cum_net_ret_pct ==")
    print(out.pivot_table(index=["gate", "coin"], columns="win",
                          values="cum_net_ret_pct").round(1).to_string())
    print(out.groupby(["gate", "win"])["cum_net_ret_pct"].mean().round(2).to_string())


if __name__ == "__main__":
    main()
