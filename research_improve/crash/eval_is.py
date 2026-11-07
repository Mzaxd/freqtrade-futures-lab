"""CRASH IS evaluation: yearly gates + slice metrics for the 6 variants (pre_reg §4)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wallet_lib import LAB, anchor_final, load_wallet

RES = LAB / "user_data" / "backtest_results"
CRASH = LAB / "research_improve" / "crash"

VARIANTS = ["crash_RVfroz", "crash_RVrank", "crash_RVpause", "crash_DDband", "crash_RV_DD", "crash_DDband65"]
# pre-registered baselines (full-window run 21-23 segment, wallet_lib extraction)
BASE = {"2021": 170.6, "2022": 114.5, "2023": 122.8}
GATES = {"2021": 165.6, "2022": 111.5, "2023": 119.8}   # pre_reg §4
SLICES = {
    "2023H2_bleed": ("2023-09-01", "2024-01-01", -10.8, 55.3),   # baseline dd, ret
    "2022H2": ("2022-05-01", "2023-01-01", -8.4, 78.0),
}


def yearly(s: pd.Series) -> dict:
    d = s.resample("D").last().dropna()
    return {str(y): round(float(g.iloc[-1] / g.iloc[0] - 1) * 100, 1) for y, g in d.groupby(d.index.year)}


def slice_metrics(s: pd.Series, a: str, b: str):
    sl = s[(s.index >= pd.Timestamp(a, tz="UTC")) & (s.index < pd.Timestamp(b, tz="UTC"))]
    dd = sl / sl.cummax() - 1
    return round(float(dd.min()) * 100, 1), round(float(sl.iloc[-1] / sl.iloc[0] - 1) * 100, 1)


ZIPMAP = {  # --export-filename deprecated in this freqtrade; default names mapped via meta.json
    "crash_RVfroz": "backtest-result-2026-11-07_04-52-00.zip",
    "crash_RVrank": "backtest-result-2026-11-07_04-52-20.zip",
    "crash_RVpause": "backtest-result-2026-11-07_04-52-41.zip",
    "crash_DDband": "backtest-result-2026-11-07_04-53-01.zip",
    "crash_RV_DD": "backtest-result-2026-11-07_04-53-21.zip",
    "crash_DDband65": "backtest-result-2026-11-07_04-53-42.zip",
}

rows = {}
for v in VARIANTS:
    w = load_wallet(RES / ZIPMAP[v], v)
    y = yearly(w)
    sl = {k: slice_metrics(w, a, b) for k, (a, b, _, _) in SLICES.items()}
    total = float(w.iloc[-1] / w.iloc[0] - 1) * 100
    gates = {yr: (y[yr] >= g) for yr, g in GATES.items()}
    rows[v] = {"yearly": y, "total": round(total, 1), "gates": gates,
               "all_gates_pass": all(gates.values()), "slices": sl}

print(f"{'variant':<16} {'2021':>7} {'2022':>7} {'2023':>7} {'total%':>9} "
      f"{'23H2dd':>7} {'23H2ret':>8} {'22H2dd':>7} {'22H2ret':>8}  G1G2G3")
for v, r in rows.items():
    y = r["yearly"]
    s23, s22 = r["slices"]["2023H2_bleed"], r["slices"]["2022H2"]
    print(f"{v:<16} {y['2021']:>7} {y['2022']:>7} {y['2023']:>7} {r['total']:>9} "
          f"{s23[0]:>7} {s23[1]:>8} {s22[0]:>7} {s22[1]:>8}  {'PASS' if r['all_gates_pass'] else 'FAIL ' + str([k for k, ok in r['gates'].items() if not ok])}")
print(f"baseline        {BASE['2021']:>7} {BASE['2022']:>7} {BASE['2023']:>7} {'~1194':>9} {-10.8:>7} {55.3:>8} {-8.4:>7} {78.0:>8}")

(CRASH / "is_results.json").write_text(json.dumps(rows, indent=2))
print("\nwrote", CRASH / "is_results.json")
