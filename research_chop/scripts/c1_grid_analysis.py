# c1_grid_analysis.py — WS-C1 IS grid summary + winner selection (rule:
# highest IS Calmar among configs with >=30 trades; runner-up disclosed).
# Reads the 8 verified zips in research_chop/results/, prints a full table,
# and per-config standalone trade economics (win rate, avg net pnl, fee share,
# funding). Also emits a machine-readable summary csv in research_chop/logs/.
# Run: .venv/Scripts/python.exe research_chop/scripts/c1_grid_analysis.py
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "research_chop" / "results"
LOGS = ROOT / "research_chop" / "logs"

CONFIGS = [
    "g2_96_20", "g2_96_25", "g2_168_20", "g2_168_25",
    "g4_96_20", "g4_96_25", "g4_168_20", "g4_168_25",
]


def load(tag: str):
    with zipfile.ZipFile(RES / f"chop_c1_is_{tag}.zip") as f:
        main = [n for n in f.namelist() if n.endswith(".json")
                and "_config" not in n and "_market_change" not in n][0]
        d = json.loads(f.read(main))
    assert list(d["strategy"].keys()) == [f"CHOP_MR_{tag}"], f"key mismatch for {tag}"
    return d["strategy"][f"CHOP_MR_{tag}"]


def econ(s: dict) -> dict:
    t = pd.DataFrame(s["trades"])
    fees = (t["stake_amount"] * t["leverage"]) * (t["fee_open"] + t["fee_close"])
    notional = t["stake_amount"] * t["leverage"]
    net = t["profit_abs"]                      # freqtrade profit_abs already net of fees+funding
    fund = t["funding_fees"].abs().sum()
    return {
        "n": len(t),
        "win%": round(100.0 * (t["profit_abs"] > 0).mean(), 1),
        "avg_net_usdt": round(net.mean(), 2),
        "avg_net_bps_notional": round(1e4 * (net / notional).mean(), 2),
        "fees_usdt": round(fees.sum(), 1),
        "funding_usdt": round(fund, 1),
        "fee+fnd/gross_win": round(
            (fees.sum() + fund) / t.loc[t["profit_abs"] > 0, "profit_abs"].sum(), 3)
        if (t["profit_abs"] > 0).any() else np.nan,
        "exit_stop%": round(100.0 * (t["exit_reason"] == "stop_loss").mean(), 1),
        "exit_mid%": round(100.0 * (t["exit_reason"].isin(
            ["exit_signal"])).mean(), 1),
        "exit_time%": round(100.0 * (t["exit_reason"] == "mr_time_48h").mean(), 1),
    }


def main() -> None:
    rows = []
    for tag in CONFIGS:
        s = load(tag)
        e = econ(s)
        rows.append({
            "config": tag, "trades": s["trade_count"] if "trade_count" in s else len(s["trades"]),
            "profit%": round(100 * s["profit_total"], 1),
            "CAGR%": round(100 * s["cagr"], 1),
            "Sharpe": round(s["sharpe"], 2),
            "Calmar": round(s["calmar"], 2),
            "maxDD%": round(100 * s["max_drawdown_account"], 1),
            "prof_fact": round(s["profit_factor"], 2),
            **e,
        })
    df = pd.DataFrame(rows)
    print("=== WS-C1 IS grid (2021-01-01 .. 2024-01-01, 3 pairs, lev2, fee 5bp/side) ===")
    print(df.to_string(index=False))
    elig = df[df["trades"] >= 30]
    best = elig.loc[elig["Calmar"].idxmax()]
    run = elig["Calmar"].sort_values(ascending=False).index[1]
    print(f"\nWINNER (IS Calmar max, trades>=30): {best['config']}  "
          f"Calmar={best['Calmar']}, trades={int(best['trades'])}, profit={best['profit%']}%")
    print(f"RUNNER-UP: {df.loc[run, 'config']}  Calmar={df.loc[run, 'Calmar']}, trades={int(df.loc[run, 'trades'])}")
    # gate-level best (pre-registered g2-vs-g4 decision)
    for g in ("g2", "g4"):
        sub = elig[elig["config"].str.startswith(g)]
        b = sub.loc[sub["Calmar"].idxmax()]
        print(f"gate {g} best: {b['config']} Calmar={b['Calmar']} (gate-level winner: "
              f"{'g2' if g == 'g2' else 'g4'})")
    LOGS.mkdir(parents=True, exist_ok=True)
    df.to_csv(LOGS / "c1_is_grid_summary.csv", index=False)
    print("\nsaved -> research_chop/logs/c1_is_grid_summary.csv")


if __name__ == "__main__":
    main()
