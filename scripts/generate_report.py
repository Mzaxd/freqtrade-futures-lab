#!/usr/bin/env python
"""Generate equity & drawdown curves + a per-strategy markdown report from a
backtest result zip. Usage: python scripts/generate_report.py ZIP LABEL
Writes user_data/reports/curve_<LABEL>.png and equity_<LABEL>.csv
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "user_data/reports"


def main():
    zip_path = Path(sys.argv[1])
    label = sys.argv[2]
    with zipfile.ZipFile(zip_path) as z:
        jname = [n for n in z.namelist() if n.endswith(".json") and "config" not in n and "market" not in n][0]
        data = json.loads(z.read(jname))
    strat = list(data["strategy"].keys())[0]
    s = data["strategy"][strat]
    trades = pd.DataFrame(s["trades"])
    if trades.empty:
        print("no trades, skip")
        return
    trades["close_date"] = pd.to_datetime(trades["close_date"], utc=True)
    trades = trades.sort_values("close_date")
    start_bal = s.get("starting_balance", 10000)
    trades["equity"] = start_bal + trades["profit_abs"].cumsum()
    eq = trades.set_index("close_date")["equity"]
    dd = (eq / eq.cummax() - 1.0) * 100

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    axes[0].plot(eq.index, eq.values, lw=1.2, color="tab:blue")
    axes[0].set_title(f"{strat} - {label}  |  trades {s['total_trades']}  "
                      f"profit {s['profit_total']*100:.1f}%  maxDD {s['max_drawdown_account']*100:.1f}%  "
                      f"sharpe {s.get('sharpe', 0):.2f}")
    axes[0].set_ylabel("Equity (USDT)")
    axes[0].grid(alpha=0.3)
    axes[1].fill_between(dd.index, dd.values, 0, color="tab:red", alpha=0.5)
    axes[1].set_ylabel("Drawdown %")
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_png = REPORTS / f"curve_{label}.png"
    fig.savefig(out_png, dpi=110)
    pd.DataFrame({"equity": eq, "drawdown_pct": dd}).to_csv(REPORTS / f"equity_{label}.csv")
    print(f"wrote {out_png}")


if __name__ == "__main__":
    main()
