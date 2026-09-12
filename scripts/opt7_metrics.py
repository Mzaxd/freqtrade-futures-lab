#!/usr/bin/env python
"""OPT7 S1 — compact metrics extractor for a freqtrade backtest result zip."""
import sys
import zipfile
import io
import json


def metrics(zip_path: str) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "config" not in n and "market_change" not in n]
        js = json.load(io.BytesIO(z.read(names[0])))
    s = list(js["strategy"].values())[0]
    keys = [
        "backtest_start", "backtest_end", "total_trades", "wins", "losses",
        "profit_total", "profit_total_abs", "profit_factor", "max_drawdown_account",
        "trade_count_long", "trade_count_short", "winrate", "winning_trades", "losing_trades",
        "cagr", "calmar", "sharpe", "sortino", "expectancy_ratio", "profit_mean",
        "holding_avg_s", "fee_open", "fee_close",
    ]
    out = {k: s.get(k) for k in keys}
    # monthly profits if present
    if isinstance(s.get("profit_month"), list):
        out["n_months"] = len([x for x in s["profit_month"] if x is not None])
    return out


if __name__ == "__main__":
    for zp in sys.argv[1:]:
        m = metrics(zp)
        name = zp.split("/")[-1].replace(".zip", "")
        hold_h = (m.get("holding_avg_s") or 0) / 3600
        print(f"{name:42s} trades={m['total_trades']:4d} L/S={m['trade_count_long']}/{m['trade_count_short']} "
              f"win%={((m['wins'] or 0)/max(m['total_trades'],1))*100:5.1f} "
              f"profit={m['profit_total']*100:8.1f}% PF={m['profit_factor']:6.2f} "
              f"maxDD={m['max_drawdown_account']*100:5.2f}% cagr={m['cagr']*100 if m['cagr'] is not None else float('nan'):7.1f}% "
              f"sharpe={m['sharpe']:5.2f} avg_hold_h={hold_h:5.1f} exp_r={m['expectancy_ratio']}")
