"""LVG IS evaluation (21-23 only): sleeve yearly + combined-with-baseline
portfolio, per pre_reg.md selection rule. Prints a table; no 24-26 data.
"""
import sys

sys.path.insert(0, "research_improve/lvg")
from eval_lib import (BASE_A_ZIP, BASE_B_ZIP, dd30_by_year, load_zip, portfolio,
                      report, yearly)

CUT = "2024-01-01"

_, A_base, _, _, _ = load_zip(BASE_A_ZIP)
_, B_base, _, _, _ = load_zip(BASE_B_ZIP)

print("=== baseline sleeves IS ===")
print(report("A_base", A_base.loc[:CUT]))
print(report("B_base", B_base.loc[:CUT]))
print(report("P_base", portfolio(A_base, B_base).loc[:CUT]))

A_CELLS = ["lvg_is_a_vt60", "lvg_is_a_vt60f1", "lvg_is_a_vt50", "lvg_is_a_r2"]
B_CELLS = ["lvg_is_b_15x", "lvg_is_b_2x", "lvg_is_b_2xvt"]

print("\n=== line 1: A variant + baseline B (portfolio) ===")
for tag in A_CELLS:
    try:
        s, cur, st, anchor, liqs = load_zip(f"user_data/backtest_results/{tag}.zip")
    except FileNotFoundError:
        print(f"{tag}: MISSING")
        continue
    p = portfolio(cur, B_base).loc[:CUT]
    print(report(f"{tag} (liq={liqs})", p))
    print("   sleeve-A yearly:", yearly(cur.loc[:CUT]).round(1).to_dict())

print("\n=== line 2: baseline A + B variant (portfolio) ===")
for tag in B_CELLS:
    try:
        s, cur, st, anchor, liqs = load_zip(f"user_data/backtest_results/{tag}.zip")
    except FileNotFoundError:
        print(f"{tag}: MISSING")
        continue
    p = portfolio(A_base, cur).loc[:CUT]
    print(report(f"{tag} (liq={liqs})", p))
    print("   sleeve-B yearly:", yearly(cur.loc[:CUT]).round(1).to_dict())
