"""WS-C0 deliverable 4: funding-harvest ceiling per coin, IS/OS split.

Two measures on {PAIR}-1h-funding_rate.feather (8h settlement events, rate in
decimal per event; 1 bp = 0.0001):

(a) perfect_foresight  = sum |rate| over in-window events (always on the
    receiving side of every event). NOT implementable (settlement rate at time
    T is only fixed at T); a pure upper bound.
(b) simple_rule_causal  = position side decided by the PREVIOUS event's settled
    rate (rate>0 -> short, rate<0 -> long; flips allowed at every event).
    pnl_k = sign(rate_{k-1}) * rate_k  (equal to +|rate_k| when the sign
    persists, -|rate_k| when it flips against you).

Both assume: 1x notional held continuously, ZERO price risk (delta-hedged),
zero transaction/funding costs on flips -- the "pure rate flow" assumption.
This is deliberately optimistic and disclosed as such.

Outputs (research_chop/logs/): ws_c0_funding_ceiling.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEATHER = ROOT / "user_data" / "data" / "binance" / "futures"
LOGS = ROOT / "research_chop" / "logs"
COINS = ["BTC", "ETH", "SOL"]
WINDOWS = {"IS": ("2021-01-01", "2023-12-31 23:59"),
           "OS": ("2024-01-01", "2026-09-12 23:59")}


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    rows = []
    for coin in COINS:
        fr = pd.read_feather(FEATHER / f"{coin}_USDT_USDT-1h-funding_rate.feather")
        fr = fr.set_index("date").sort_index()["funding_rate"]
        for win, (w0, w1) in WINDOWS.items():
            w0, w1 = pd.Timestamp(w0, tz="UTC"), pd.Timestamp(w1, tz="UTC")
            sub = fr.loc[w0:w1]
            prev_rate = fr.loc[:w0].iloc[:-1]
            # causal continuity: side for the first in-window event comes from
            # the last settled event BEFORE the window (past data, no lookahead)
            prev0 = prev_rate.iloc[-1] if len(prev_rate) else np.nan
            r = sub.to_numpy()
            a_bps = float(np.abs(r).sum()) * 1e4
            prev = np.concatenate([[prev0], r[:-1]])
            b_pnl = np.sign(prev) * r
            b_pnl = np.nan_to_num(b_pnl, nan=0.0)  # first-event side unknown -> 0 pnl
            b_bps = float(b_pnl.sum()) * 1e4
            years = (sub.index[-1] - sub.index[0]).total_seconds() / (365.25 * 86400)
            rows.append({
                "coin": coin, "win": win, "n_events": len(sub),
                "years": round(years, 2),
                "perfect_bps": round(a_bps, 1),
                "perfect_ann_bps": round(a_bps / years, 1),
                "simple_bps": round(b_bps, 1),
                "simple_ann_bps": round(b_bps / years, 1),
                "flip_events_against": int((np.sign(prev) * r < 0).sum()),
                "mean_abs_rate_bps": round(float(np.abs(r).mean()) * 1e4, 2)})
    out = pd.DataFrame(rows)
    out.to_csv(LOGS / "ws_c0_funding_ceiling.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
