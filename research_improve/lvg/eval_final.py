"""LVG single-shot adjudication (24-26 included, per pre_reg.md).

Evaluates:
1. baseline AB70/30 (reference, full window)
2. selected combo: LVG_A_r2 (7000) + LVG_B_2xvt (3000), full window
3. line 3: offline vol-scaling of baseline AB at T_p=20 (selected on IS)
Acceptance: 2023>+148.6, 2024>+107.7, 2025>-7.4 & >0, 2026>-15.1 & >0,
portfolio dd30 (daily, 30d rolling) >= -20% everywhere.
"""
import sys

import numpy as np

sys.path.insert(0, "research_improve/lvg")
from eval_lib import (BASE_A_ZIP, BASE_B_ZIP, anchor_tail, dd30_by_year, load_zip,
                      portfolio, yearly)

BENCH = {2021: None, 2022: None, 2023: 148.6, 2024: 107.7, 2025: -7.4, 2026: -15.1}


def show(name, p, bench=True):
    y = yearly(p)
    d = dd30_by_year(p)
    ok = []
    for yr, b in BENCH.items():
        if b is None or yr not in y.index:
            continue
        v = y.get(yr, float("nan"))
        if yr in (2023, 2024):
            ok.append((yr, v > b))
        else:
            ok.append((yr, (v > b) and (v > 0)))
    redline = d.min() >= -20.0
    print(f"--- {name}")
    print("  yearly%:", {int(k): round(v, 1) for k, v in y.items()})
    print("  dd30min%:", {int(k): round(v, 1) for k, v in d.items()}, "| all:", round(d.min(), 1))
    print("  acceptance:", {yr: ("PASS" if c else "FAIL") for yr, c in ok}, "| dd30 red line:", "PASS" if redline else "FAIL")
    return y, d


# --- baselines (reference) ---
_, A_base, stA, anchA, liqA = load_zip(BASE_A_ZIP)
_, B_base, stB, anchB, liqB = load_zip(BASE_B_ZIP)
A_base = anchor_tail(A_base, anchA, "2026")
B_base = anchor_tail(B_base, anchB, "2026")
show("baseline AB70/30 (reference)", portfolio(A_base, B_base))

# --- selected combo, single shot ---
_, A_r2, stA2, anchA2, liqA2 = load_zip("user_data/backtest_results/lvg_full_a_r2.zip")
_, B_vt, stB2, anchB2, liqB2 = load_zip("user_data/backtest_results/lvg_full_b_2xvt.zip")
print(f"A_r2 full: final={stA2['final_balance']:.0f} anchor={anchA2:.0f} liq={liqA2} trades={stA2['total_trades']}")
print(f"B_2xvt full: final={stB2['final_balance']:.0f} anchor={anchB2:.0f} liq={liqB2} trades={stB2['total_trades']}")
A_r2 = anchor_tail(A_r2, anchA2, "2026")
B_vt = anchor_tail(B_vt, anchB2, "2026")
show("LVG combo: A_r2 + B_2xvt (SINGLE SHOT)", portfolio(A_r2, B_vt))
show("  sleeve A_r2", A_r2, bench=False)
show("  sleeve B_2xvt", B_vt, bench=False)

# --- line 3: offline equal-vol scaling of the baseline portfolio, T_p=20 ---
P = portfolio(A_base, B_base)
d = P.resample("D").last()
r = d.pct_change().dropna()
m = (20.0 / (r.rolling(30).std() * np.sqrt(365) * 100)).shift(1).clip(0.5, 2.0)
rs = (r * m).fillna(0)
eq = (1 + rs).cumprod() * 10000
eq.index.name = "date"
show("line3 offline T_p=20 on baseline AB (paper)", eq)
print("  (paper overlay: frictionless, no funding/borrow costs; shape only)")
