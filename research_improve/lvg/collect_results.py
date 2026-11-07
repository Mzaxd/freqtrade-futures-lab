"""LVG — collect results.json (v2, attribution-correct).

Attribution conventions (documented in report.md):
- yearly: REALIZED attribution from the wallet feather (identical to how the
  CONTEXT baselines were computed: a trade's PnL lands in the year it closes).
  For runs that END with force-closed open trades (IS B cells: Oct-2023 basket
  force-closed 2024-01-01; full A_r2: 3 trades open at 2026-11-07), the raw
  feather EXCLUDES that PnL -> additionally report 'final_year_anchored'
  (terminal-year return with the JSON profit_total_abs anchor applied).
- final_balance: JSON final_balance (includes force-close PnL).
- dd30: on the raw curve, and for terminal-2026 runs also anchored dd30.
"""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research_improve/lvg")
from eval_lib import (BASE_A_ZIP, BASE_B_ZIP, anchor_tail, dd30_by_year, load_zip,
                      portfolio, yearly)

RUNS = [
    ("lvg_is_a_vt60", "user_data/backtest_results/lvg_is_a_vt60.zip",
     "freqtrade backtesting --userdir user_data --config user_data/configs/config_futures.json --strategy-path user_data/strategies/oss --strategy LVG_A_vt60 --timerange 20210101-20240101 --max-open-trades 4 --dry-run-wallet 3000->7000 --cache none --export trades"),
    ("lvg_is_a_vt60f1", "user_data/backtest_results/lvg_is_a_vt60f1.zip",
     "same but --strategy LVG_A_vt60f1 (T=60.6 clamp[1.0,2.0])"),
    ("lvg_is_a_vt50", "user_data/backtest_results/lvg_is_a_vt50.zip",
     "same but --strategy LVG_A_vt50 (T=50.6 clamp[0.5,1.5])"),
    ("lvg_is_a_r2", "user_data/backtest_results/lvg_is_a_r2.zip",
     "same but --strategy LVG_A_r2 (constant risk x2)"),
    ("lvg_is_b_15x", "user_data/backtest_results/lvg_is_b_15x.zip",
     "freqtrade backtesting ... --strategy LVG_B_15x --timerange 20210101-20240101 --max-open-trades 3 --dry-run-wallet 3000 --cache none --export trades"),
    ("lvg_is_b_2x", "user_data/backtest_results/lvg_is_b_2x.zip",
     "same but --strategy LVG_B_2x (fixed 2.0x)"),
    ("lvg_is_b_2xvt", "user_data/backtest_results/lvg_is_b_2xvt.zip",
     "same but --strategy LVG_B_2xvt (lev=clamp(2*60.6/RV30,1,2.5))"),
    ("lvg_full_a_r2", "user_data/backtest_results/lvg_full_a_r2.zip",
     "freqtrade backtesting ... --strategy LVG_A_r2 --timerange 20210101- --max-open-trades 4 --dry-run-wallet 7000 --cache none --export trades"),
    ("lvg_full_b_2xvt", "user_data/backtest_results/lvg_full_b_2xvt.zip",
     "freqtrade backtesting ... --strategy LVG_B_2xvt --timerange 20210101- --max-open-trades 3 --dry-run-wallet 3000 --cache none --export trades"),
    ("baseline_A_ARL_2x", BASE_A_ZIP, "pre-existing (CONTEXT section 2)"),
    ("baseline_B_OPT2", BASE_B_ZIP, "pre-existing (CONTEXT section 2)"),
]

out = []
curves_raw, curves_anch = {}, {}
for tag, zpath, cmd in RUNS:
    s, cur, st, anchor, liqs = load_zip(zpath)
    anch = anchor_tail(cur, anchor, "2026")
    curves_raw[tag] = cur
    curves_anch[tag] = anch
    y = yearly(cur)
    d_raw = dd30_by_year(cur)
    d_anch = dd30_by_year(anch)
    final_year = int(cur.index[-1].year)
    rec = {
        "tag": tag, "strategy": s, "cmd": cmd, "zip": zpath,
        "start_wallet": st["starting_balance"],
        "final_balance": round(st["final_balance"], 1),
        "profit_total_pct": round(st["profit_total"] * 100, 1),
        "liquidations": liqs,
        "trades": st["total_trades"],
        "left_open_at_end": len(st.get("left_open_trades", [])),
        "yearly_realized": {str(int(k)): round(float(v), 1) for k, v in y.items()},
        "final_year_anchored": {str(final_year): round(float(yearly(anch).iloc[-1]), 1)},
        "maxdd_pct": round(st["max_drawdown_account"] * 100, 1),
        "dd30_min_by_year": {str(int(k)): round(float(v), 1) for k, v in d_raw.items()},
        "dd30_min_all": round(float(d_raw.min()), 1),
        "dd30_min_all_anchored": round(float(d_anch.min()), 1),
    }
    out.append(rec)

# combos (offline synthesis; yearly realized + anchored 2026)
for nm, at, bt in (("combo_full_r2_plus_2xvt", "lvg_full_a_r2", "lvg_full_b_2xvt"),
                   ("combo_baseline_AB7030", "baseline_A_ARL_2x", "baseline_B_OPT2")):
    P = portfolio(curves_raw[at], curves_raw[bt])
    Pa = portfolio(curves_anch[at], curves_anch[bt])
    y, d = yearly(P), dd30_by_year(P)
    out.append({
        "tag": nm, "strategy": f"{at} + {bt} (offline synth 7000/3000)",
        "cmd": "offline portfolio synthesis per CONTEXT section 6", "zip": None,
        "start_wallet": 10000, "final_balance": round(float(Pa.iloc[-1]), 0),
        "yearly_realized": {str(int(k)): round(float(v), 1) for k, v in y.items()},
        "final_year_anchored": {"2026": round(float(yearly(Pa).iloc[-1]), 1)},
        "dd30_min_by_year": {str(int(k)): round(float(v), 1) for k, v in d.items()},
        "dd30_min_all": round(float(d.min()), 1),
        "dd30_min_all_anchored": round(float(dd30_by_year(Pa).min()), 1),
    })

# line 3 paper overlay on baseline combo (raw attribution), T_p=20 (IS-selected)
Pb = curves_anch["baseline_A_ARL_2x"] + 0  # placeholder, use raw below
Pb = portfolio(curves_raw["baseline_A_ARL_2x"], curves_raw["baseline_B_OPT2"])
r = Pb.resample("D").last().pct_change().dropna()
m = (20.0 / (r.rolling(30).std() * np.sqrt(365) * 100)).shift(1).clip(0.5, 2.0)
eq = ((r * m).fillna(0) + 1).cumprod() * 10000
y, d = yearly(eq), dd30_by_year(eq)
out.append({
    "tag": "line3_offline_Tp20_paper", "strategy": "baseline AB70/30 x vol-scaling T_p=20 (paper)",
    "cmd": "offline r*(20/RV30p(t-1)) clamp[0.5,2] on baseline daily returns (raw attribution)",
    "zip": None, "start_wallet": 10000, "final_balance": round(float(eq.iloc[-1]), 0),
    "yearly_realized": {str(int(k)): round(float(v), 1) for k, v in y.items()},
    "dd30_min_by_year": {str(int(k)): round(float(v), 1) for k, v in d.items()},
    "dd30_min_all": round(float(d.min()), 1),
    "note": "frictionless paper overlay (no funding/borrow/txn costs); shape only",
})

with open("research_improve/lvg/results.json", "w") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print("records:", len(out))
for r_ in out:
    print(r_["tag"], "| final:", r_["final_balance"],
          "| yearly:", r_["yearly_realized"],
          "| anch26:", r_.get("final_year_anchored"),
          "| dd30:", r_["dd30_min_all"], "/", r_.get("dd30_min_all_anchored"))
