#!/usr/bin/env python
"""OPT7_s4_results.py — Phase 7 S4: collect OPT7_FreqaiOwn backtest results.

Scans user_data/backtest_results/*.zip (skipping already-seen opt7_s4_* copies),
finds results whose strategy key is OPT7_FreqaiOwn, and prints one summary line
per run (identified by backtest timerange from meta files).

Usage: OPT7_s4_results.py            # print all OPT7_FreqaiOwn runs found
"""
from __future__ import annotations

import glob
import json
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
RESULTS = BASE / "user_data" / "backtest_results"

KEYS = [
    "total_trades",
    "profit_total",
    "profit_total_pct",  # not present, computed below
    "profit_factor",
    "max_drawdown_account",
    "sharpe",
    "sortino",
    "winrate",
    "wins",
    "losses",
    "trade_count_long",
    "trade_count_short",
    "backtest_start",
    "backtest_end",
]


def read_zip(zp: Path):
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist() if n.endswith(".json") or n.endswith(".json.gz")]
        if not names:
            return None
        payload = z.read(names[0])
    if names[0].endswith(".gz"):
        import gzip

        payload = gzip.decompress(payload)
    return json.loads(payload)


def main():
    rows = []
    for zp in sorted(RESULTS.glob("backtest-result-*.zip")):
        try:
            data = read_zip(zp)
        except Exception:
            continue
        if not data:
            continue
        strats = data.get("strategy", {})
        for sname, s in strats.items():
            if sname != "OPT7_FreqaiOwn":
                continue
            rows.append(
                {
                    "file": zp.name,
                    "profit_pct": s.get("profit_total", 0) * 100,
                    "trades": s.get("total_trades", 0),
                    "pf": s.get("profit_factor"),
                    "dd_pct": s.get("max_drawdown_account", 0) * 100
                    if s.get("max_drawdown_account") is not None
                    else None,
                    "sharpe": s.get("sharpe"),
                    "sortino": s.get("sortino"),
                    "winrate": s.get("winrate", 0) * 100,
                    "longs": s.get("trade_count_long"),
                    "shorts": s.get("trade_count_short"),
                    "start": s.get("backtest_start", "")[:10],
                    "end": s.get("backtest_end", "")[:10],
                }
            )
    print(f"{'file':44s} {'range':24s} {'profit%':>8s} {'trades':>7s} {'PF':>5s} {'DD%':>6s} {'Sharpe':>7s} {'win%':>5s} L/S")
    for r in rows:
        pf = f"{r['pf']:.2f}" if r["pf"] is not None else "n/a"
        sh = f"{r['sharpe']:.2f}" if r["sharpe"] is not None else "n/a"
        print(
            f"{r['file']:44s} {r['start']}->{r['end']:10s} {r['profit_pct']:8.2f} {r['trades']:7d} {pf:>5s} "
            f"{r['dd_pct']:6.1f} {sh:>7s} {r['winrate']:5.1f} {r['longs']}/{r['shorts']}"
        )


if __name__ == "__main__":
    main()
