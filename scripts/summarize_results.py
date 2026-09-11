#!/usr/bin/env python
"""Summarize freqtrade backtest result zip(s) into one CSV + markdown table.

Usage:
  python scripts/summarize_results.py OUT_TAG ZIP1 [ZIP2 ...]

Writes:
  user_data/reports/summary_{OUT_TAG}.csv
  user_data/reports/summary_{OUT_TAG}.md
Each input zip gets one row. Metrics beyond freqtrade's own (fee cost, funding
cost, liquidation count) are computed from the per-trade records.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "user_data/backtest_results"
REPORTS = ROOT / "user_data/reports"

COLS = [
    "label", "strategy", "timerange", "trades", "profit_total_pct", "cagr_pct",
    "max_drawdown_pct", "dd_duration_days", "sharpe", "sortino", "calmar",
    "profit_factor", "winrate_pct", "avg_profit_pct", "expectancy_ratio",
    "trades_long", "trades_short", "avg_duration_h", "fee_cost_usdt",
    "funding_cost_usdt", "liquidations", "market_change_pct", "final_balance",
]


def load_result(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        jname = [
            n for n in z.namelist()
            if n.endswith(".json") and "config" not in n and "market" not in n
        ][0]
        return json.loads(z.read(jname))


def one_row(label: str, zip_path: Path) -> dict:
    data = load_result(zip_path)
    out = {"label": label}
    for strat_name, s in data["strategy"].items():
        trades = pd.DataFrame(s["trades"])
        fee_cost = float((trades["amount"] * trades["open_rate"] * trades["fee_open"]
                          + trades["amount"] * trades["close_rate"] * trades["fee_close"]).sum())
        funding_cost = float(trades["funding_fees"].sum())
        liq = int((trades["exit_reason"] == "liquidation").sum())
        # funding_fees sign in freqtrade: positive = cost to the trade? we report magnitude split by sign
        out.update({
            "strategy": strat_name,
            "timerange": f'{s["backtest_start"]} -> {s["backtest_end"]}',
            "trades": s["total_trades"],
            "profit_total_pct": round(s["profit_total"] * 100, 2),
            "cagr_pct": round((s.get("cagr") or 0) * 100, 2),
            "max_drawdown_pct": round(s["max_drawdown_account"] * 100, 2),
            "dd_duration_days": round((s.get("drawdown_duration_s") or 0) / 86400, 1),
            "sharpe": round(s.get("sharpe") or 0, 2),
            "sortino": round(s.get("sortino") or 0, 2),
            "calmar": round(s.get("calmar") or 0, 2),
            "profit_factor": round(s.get("profit_factor") or 0, 2),
            "winrate_pct": round((s.get("winrate") or 0) * 100, 1),
            "avg_profit_pct": round(s["profit_mean"] * 100, 2),
            "expectancy_ratio": round(s.get("expectancy_ratio") or 0, 2),
            "trades_long": s.get("trade_count_long", 0),
            "trades_short": s.get("trade_count_short", 0),
            "avg_duration_h": round((s.get("holding_avg_s") or 0) / 3600, 1),
            "fee_cost_usdt": round(fee_cost, 2),
            "funding_cost_usdt": round(funding_cost, 2),
            "liquidations": liq,
            "market_change_pct": round((s.get("market_change") or 0) * 100, 1),
            "final_balance": round(s.get("final_balance") or 0, 2),
        })
    return out


def main():
    tag = sys.argv[1]
    rows = [one_row(Path(a).name.replace(".zip", ""), Path(a)) for a in sys.argv[2:]]
    df = pd.DataFrame(rows)[COLS]
    REPORTS.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS / f"summary_{tag}.csv"
    md_path = REPORTS / f"summary_{tag}.md"
    df.to_csv(csv_path, index=False)
    with open(md_path, "w") as f:
        f.write(f"# Backtest summary: {tag}\n\n")
        f.write(f"Generated from: {[Path(a).name for a in sys.argv[2:]]}\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n")
    print(df.to_string(index=False))
    print(f"\nwrote {csv_path} and {md_path}")


if __name__ == "__main__":
    main()
