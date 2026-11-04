"""WS-C0 deliverable 1: gate ON-segment inventory (descriptive).

Enumerates maximal ON runs (>=48h) for g1/g2/g4 per coin over the pre-registered
window 2021-01-01 .. 2026-09-12 23:00 UTC. Descriptive only (raw label runs, no
shift): row t labels use <=t data; a tradable entry would only be possible from
t+1 (disclosed in report). Segment-wise BTC same-period close return is computed
from regime_1h_BTC.csv closes at the segment's first/last row.

Outputs (research_chop/logs/):
  ws_c0_segments_{COIN}_{gate}.csv   full >=48h segment lists
  ws_c0_inventory_summary.csv        per coin x gate summary
  ws_c0_inventory_yearly.csv         per year x coin x gate ON-day counts
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research_chop" / "data"
LOGS = ROOT / "research_chop" / "logs"
COINS = ["BTC", "ETH", "SOL"]
GATES = ["g1", "g2", "g4"]
WIN_START = pd.Timestamp("2021-01-01 00:00:00+00:00")
WIN_END = pd.Timestamp("2026-09-12 23:00:00+00:00")  # inclusive, last studied hour


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Maximal True runs as (start_idx, end_idx) inclusive."""
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    lab = {c: pd.read_csv(DATA / f"regime_1h_{c}.csv", parse_dates=["date"])
           .set_index("date") for c in COINS}
    for c in COINS:
        lab[c] = lab[c].loc[WIN_START:WIN_END]
    btc_close = lab["BTC"]["close"]

    summaries, yearly_rows = [], []
    for coin in COINS:
        df = lab[coin]
        years = df.index.year
        for gate in GATES:
            mask = df[gate].to_numpy(dtype=bool)
            segs = [(s, e) for s, e in runs(mask) if e - s + 1 >= 48]
            seg_rows = []
            for s, e in segs:
                t0, t1 = df.index[s], df.index[e]
                btc0, btc1 = btc_close.reindex([t0, t1], method="nearest").to_numpy()
                seg_rows.append({
                    "start": t0, "end": t1, "hours": e - s + 1,
                    "days": round((e - s + 1) / 24, 2),
                    "btc_ret_pct": round((btc1 / btc0 - 1) * 100, 2)})
            seg_df = pd.DataFrame(seg_rows, columns=["start", "end", "hours", "days", "btc_ret_pct"])
            seg_df.to_csv(LOGS / f"ws_c0_segments_{coin}_{gate}.csv",
                          index=False, columns=["start", "end", "hours", "days", "btc_ret_pct"])

            hrs_all = int(mask.sum())
            hrs_seg = int(sum(e - s + 1 for s, e in segs))
            summaries.append({
                "coin": coin, "gate": gate,
                "occ_pct": round(100 * hrs_all / len(df), 2),
                "on_days_total": round(hrs_all / 24, 1),
                "n_segments_ge48h": len(segs),
                "on_days_in_ge48h": round(hrs_seg / 24, 1),
                "share_on_in_ge48h_pct": round(100 * hrs_seg / max(hrs_all, 1), 2),
                "longest_hours": int(seg_df["hours"].max()) if len(seg_df) else 0})

            for y in sorted(set(years)):
                m = np.asarray(years == y)
                hrs_y = int(mask[m].sum())
                hrs_y_seg = 0
                for s, e in segs:
                    ys = df.index[s].year
                    # attribute each segment hour to its own calendar year
                    idx = df.index[s:e + 1]
                    hrs_y_seg += int((idx.year == y).sum())
                yearly_rows.append({
                    "coin": coin, "gate": gate, "year": y,
                    "on_days_all": round(hrs_y / 24, 2),
                    "on_days_in_ge48h_segs": round(hrs_y_seg / 24, 2),
                    "hours_in_window": int(m.sum())})

    pd.DataFrame(summaries).to_csv(LOGS / "ws_c0_inventory_summary.csv", index=False)
    ydf = pd.DataFrame(yearly_rows)
    ydf.to_csv(LOGS / "ws_c0_inventory_yearly.csv", index=False)

    print("== summary (window 2021-01-01 .. 2026-09-12) ==")
    print(pd.DataFrame(summaries).to_string(index=False))
    print("\n== top-10 longest segments per coin x gate ==")
    for coin in COINS:
        for gate in GATES:
            d = pd.read_csv(LOGS / f"ws_c0_segments_{coin}_{gate}.csv",
                            parse_dates=["start", "end"])
            if d.empty:
                print(f"{coin} {gate}: none >=48h")
                continue
            top = d.nlargest(10, "hours")
            print(f"\n-- {coin} {gate} (n>=48h segs={len(d)}) --")
            print(top.to_string(index=False))
    print("\n== yearly ON days (all / in >=48h segs) ==")
    for gate in GATES:
        sub = ydf[ydf["gate"] == gate].pivot_table(
            index="year", columns="coin", values=["on_days_all", "on_days_in_ge48h_segs"])
        print(f"\n-- {gate} --")
        print(sub.round(1).to_string())


if __name__ == "__main__":
    main()
