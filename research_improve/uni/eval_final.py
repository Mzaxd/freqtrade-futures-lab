"""uni/step7 (agent 2) — final evaluation for report.md / results.json.

Usage: .venv/bin/python -I research_improve/uni/eval_final.py
Hardcoded arm registry (the exact commands actually run). Per zip:
wallet feather -> daily equity (terminal value anchored to profit_total_abs,
CONTEXT §6 known feather-end gap) -> calendar-year returns, per-year 30d
rolling DD min, global DD30 min. Writes results.json (CONTEXT §7 schema + cmd).
"""
import json
import os
import tempfile
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BT = "/Users/caihaohan/Code/freqtrade-futures-lab/user_data/backtest_results"

ARMS = [
    {"tag": "uni_probe_ext", "strategy": "uni_ARL_ext", "zip": f"{BT}/uni_probe_ext.zip",
     "cmd": "probe: uni_ARL_ext 20250110-20250112 pool125 MOT4 w7000 (plumbing only, 0-info)",
     "arm": "probe"},
    {"tag": "uni_full_a", "strategy": "uni_ARL_frozen12", "zip": f"{BT}/uni_full_a.zip",
     "cmd": ".venv/bin/freqtrade backtesting --userdir user_data --config user_data/configs/config_futures.json "
            "--strategy-path user_data/strategies/oss --strategy uni_ARL_frozen12 --timerange 20210101-20261107 "
            "--max-open-trades 4 -p <frozen12> --dry-run-wallet 7000 --cache none --export trades "
            "--export-filename user_data/backtest_results/uni_full_a.zip",
     "arm": "a"},
    {"tag": "uni_oos_b", "strategy": "uni_ARL_ext", "zip": f"{BT}/uni_oos_b.zip",
     "cmd": ".venv/bin/freqtrade backtesting ... --strategy uni_ARL_ext --timerange 20230101-20261107 "
            "--max-open-trades 4 -p <pool125> --dry-run-wallet 7000 --cache none --export trades "
            "--export-filename user_data/backtest_results/uni_oos_b.zip",
     "arm": "b"},
    {"tag": "uni_oos_c", "strategy": "uni_ARL_pit", "zip": f"{BT}/uni_oos_c.zip",
     "cmd": ".venv/bin/freqtrade backtesting ... --strategy uni_ARL_pit --timerange 20230101-20261107 "
            "--max-open-trades 4 -p <pool125> --dry-run-wallet 7000 --cache none --export trades "
            "--export-filename user_data/backtest_results/uni_oos_c.zip",
     "arm": "c"},
]


def load_zip(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        wf = [n for n in names if n.endswith("_wallet.feather")]
        js = [n for n in names if n.endswith(".json") and "meta" not in n and "config" not in n]
        assert wf and js, f"zip {zip_path} missing wallet/json: {names}"
        with tempfile.TemporaryDirectory() as td:
            z.extract(wf[0], td)
            z.extract(js[0], td)
            wallet = pd.read_feather(os.path.join(td, wf[0]))
            res = json.load(open(os.path.join(td, js[0])))
    strat = list(res["strategy"].keys())[0]
    return wallet, res["strategy"][strat]


def evaluate(spec):
    wallet, s = load_zip(spec["zip"])
    start_wallet = float(s["starting_balance"])
    eq = wallet.set_index("date")["total_quote"].astype(float)
    final = start_wallet + float(s["profit_total_abs"])
    eq = eq.copy()
    eq.iloc[-1] = final
    d = eq.resample("D").last().ffill()
    yearly, dd30_year = {}, {}
    dd30 = d / d.rolling(30).max() - 1
    for y, g in d.groupby(d.index.year):
        a, b = float(g.iloc[0]), float(g.iloc[-1])
        yearly[str(y)] = round((b / a - 1) * 100, 1)
        dd30_year[str(y)] = round(float(dd30[d.index.year == y].min()) * 100, 1)
    return {
        "tag": spec["tag"], "arm": spec["arm"], "cmd": spec["cmd"],
        "zip": os.path.basename(spec["zip"]),
        "start_wallet": start_wallet,
        "final_balance": round(final, 1),
        "total_return_pct": round((final / start_wallet - 1) * 100, 1),
        "yearly": yearly,
        "dd30_min_pct_by_year": dd30_year,
        "maxdd": round(float(s.get("max_drawdown_account", float("nan"))) * 100, 1),
        "dd30": round(float(dd30.min()) * 100, 1),
        "trades": int(s["total_trades"]),
    }


def main():
    rows = [evaluate(sp) for sp in ARMS if os.path.exists(sp["zip"])]
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(rows, f, indent=1)
    for r in rows:
        print(f"{r['tag']:14s} total {r['total_return_pct']:+9.1f}%  final {r['final_balance']:>10,.0f}  "
              f"dd30min {r['dd30']:6.1f}%  trades {r['trades']}")
        print("   yearly:", r["yearly"])
        print("   dd30/yr:", r["dd30_min_pct_by_year"])


if __name__ == "__main__":
    main()
