"""uni/step6 — evaluate backtest zips per CONTEXT §6 recipe.

Usage (from repo root):
  .venv/bin/python -I research_improve/uni/eval_uni.py <label>:<zip> [<label>:<zip> ...]

Per zip: extract <strategy>_wallet.feather, anchor the terminal value to
profit_total_abs + start wallet (known feather-end liquidation gap), compute
calendar-year returns (daily last -> year first/last) and the 30d rolling
drawdown minimum. Prints a table and appends rows to results.json.
"""
import json
import os
import sys
import tempfile
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def load_zip(zip_path: str):
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
    return wallet, res["strategy"][strat], strat


def evaluate(label: str, zip_path: str) -> dict:
    wallet, s, strat = load_zip(zip_path)
    start_wallet = float(s["starting_balance"])
    eq = wallet.set_index("date")["total_quote"].astype(float)
    # anchor terminal value to the JSON profit (feather end-gap fix, CONTEXT §6)
    final = start_wallet + float(s["profit_total_abs"])
    eq = eq.copy()
    eq.iloc[-1] = final
    d = eq.resample("D").last().ffill()
    yearly = {}
    for y, g in d.groupby(d.index.year):
        a, b = float(g.iloc[0]), float(g.iloc[-1])
        yearly[str(y)] = round((b / a - 1) * 100, 1)
    dd30 = (d / d.rolling(30).max() - 1)
    return {
        "tag": label,
        "strategy": strat,
        "zip": os.path.basename(zip_path),
        "start_wallet": start_wallet,
        "final_balance": round(final, 1),
        "total_return_pct": round((final / start_wallet - 1) * 100, 1),
        "yearly": yearly,
        "dd30_min_pct": round(float(dd30.min()) * 100, 1),
        "maxdd_account_pct": round(float(s.get("max_drawdown_account", float("nan"))) * 100, 1),
        "trades": int(s["total_trades"]),
    }


def main():
    rows = []
    for spec in sys.argv[1:]:
        label, zip_path = spec.split(":", 1)
        rows.append(evaluate(label, zip_path))
        r = rows[-1]
        print(f"{r['tag']:24s} total {r['total_return_pct']:+8.1f}%  final {r['final_balance']:>10,.0f}  "
              f"dd30 {r['dd30_min_pct']:6.1f}%  maxdd {r['maxdd_account_pct']:6.1f}%  trades {r['trades']}")
        print("   yearly:", r["yearly"])
    out = os.path.join(HERE, "results.json")
    existing = []
    if os.path.exists(out):
        with open(out) as f:
            existing = json.load(f)
    seen = {(r["tag"], r["zip"]) for r in existing}
    existing.extend(r for r in rows if (r["tag"], r["zip"]) not in seen)
    with open(out, "w") as f:
        json.dump(existing, f, indent=1)


if __name__ == "__main__":
    main()
