# c1_gate_check.py — WS-C1 cross-check (PRE_REG §6.2): the gate signals used
# inside CHOP_MeanRev.populate_indicators must match the dispatcher-generated
# labels research_chop/data/regime_1h_{PAIR}.csv point-by-point on sampled
# windows (>= 3, covering IS design years and the OS bleed window).
#
# Method: instantiate the strategy class directly, call populate_indicators on
# the FULL raw 1h feather (same input the backtester hands it), and compare
# mom_z / atr_pct_rank / g2 / g4 columns against the CSV on each window.
# Run: .venv/Scripts/python.exe research_chop/scripts/c1_gate_check.py
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research_chop" / "strategies"))

from CHOP_MeanRev import CHOP_MeanRev  # noqa: E402

DATA = ROOT / "user_data" / "data" / "binance" / "futures"
LAB = ROOT / "research_chop" / "data"

# sampled windows: two IS (design window) + the OS bleed window + a 2024 OS slice
WINDOWS = [
    ("IS 2021-05 (mid chop)", "2021-05-01", "2021-06-01"),
    ("IS 2022-06..09 (bear chop)", "2022-06-01", "2022-09-01"),
    ("IS 2023-10..12", "2023-10-01", "2024-01-01"),
    ("OS 2026-02-15..08-10 (bleed)", "2026-02-15", "2026-08-11"),
    ("OS 2024-04..07", "2024-04-01", "2024-07-01"),
]


def main() -> None:
    strat = CHOP_MeanRev(config={})   # base class computes BOTH g2 and g4 columns
    strat.gate = "g2"        # gate param must not affect g2_on/g4_on columns
    ok_all = True
    for pair in ("BTC", "ETH", "SOL"):
        raw = pd.read_feather(DATA / f"{pair}_USDT_USDT-1h-futures.feather")
        ind = strat.populate_indicators(raw.copy(), {"pair": f"{pair}/USDT:USDT"})
        ref = pd.read_csv(LAB / f"regime_1h_{pair}.csv", parse_dates=["date"])
        m = ind.merge(ref, on="date", suffixes=("_s", "_r"), how="inner")
        assert len(m) == len(ref), f"{pair}: row count mismatch {len(m)} vs {len(ref)}"
        print(f"\n== {pair}  merged rows={len(m)}  "
              f"{m['date'].min()} .. {m['date'].max()}")
        for wname, t0, t1 in WINDOWS:
            w = m[(m["date"] >= t0) & (m["date"] < t1)]
            dmz = (w["mom_z_s"] - w["mom_z_r"]).abs().max()
            drk = (w["atr_pct_rank_s"] - w["atr_pct_rank_r"]).abs().max()
            g2_eq = bool((w["g2_on"].astype(bool) == w["g2"].astype(bool)).all())
            g4_eq = bool((w["g4_on"].astype(bool) == w["g4"].astype(bool)).all())
            ok = (dmz < 1e-9) and (drk < 1e-12) and g2_eq and g4_eq
            ok_all &= ok
            print(f"  {wname:32s} n={len(w):5d}  max|d mom_z|={dmz:.2e}  "
                  f"max|d rank|={drk:.2e}  g2 match={g2_eq} (ON {int(w['g2'].sum())})  "
                  f"g4 match={g4_eq} (ON {int(w['g4'].sum())})  -> {'OK' if ok else 'MISMATCH'}")
    print("\nRESULT:", "ALL WINDOWS IDENTICAL" if ok_all else "MISMATCH FOUND")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
