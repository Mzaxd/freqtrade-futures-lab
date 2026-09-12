#!/usr/bin/env python
"""OPT7 S1 — NFI family inventory / ablation stats from a freqtrade backtest zip.

Usage: .venv/bin/python scripts/opt7_family_stats.py user_data/backtest_results/opt7_XXX.zip [--per-pair]

Reads the result zip (backtest-result json inside), explodes each trade's
enter_tag (space-separated family ids like "141 142") into one row per family,
and reports per-family trigger counts / coin distribution / win-rate / PF /
duration / PnL. Mixed-tag trades count once per contained family (attribution
view). Also prints a per-coin table.
"""
import sys
import zipfile
import io
import json
import pandas as pd
import numpy as np


def load_trades(zip_path: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "config" not in n and "market_change" not in n]
        js = json.load(io.BytesIO(z.read(names[0])))
    strat = list(js["strategy"].values())[0]
    rows = []
    for t in strat["trades"]:
        rows.append(
            dict(
                pair=t["pair"].split("/")[0],
                open_date=pd.Timestamp(t["open_date"]),
                close_date=pd.Timestamp(t["close_date"]),
                enter_tag=(t.get("enter_tag") or "").strip(),
                exit_reason=t.get("exit_reason") or "",
                is_short=t.get("is_short", False),
                profit_ratio=t["profit_ratio"],
                profit_abs=t["profit_abs"],
                hold_h=(pd.Timestamp(t["close_date"]) - pd.Timestamp(t["open_date"])).total_seconds() / 3600.0,
            )
        )
    return pd.DataFrame(rows)


def explode(df: pd.DataFrame) -> pd.DataFrame:
    recs = []
    for _, r in df.iterrows():
        fams = r["enter_tag"].split() or ["NONE"]
        for f in fams:
            recs.append({**r.to_dict(), "family": f})
    return pd.DataFrame(recs)


def agg(ex: pd.DataFrame) -> pd.DataFrame:
    g = ex.groupby("family")
    out = pd.DataFrame(
        dict(
            trades=g.size(),
            coins=g["pair"].nunique(),
            short_share=g["is_short"].mean().round(2),
            winrate=g.apply(lambda x: (x["profit_ratio"] > 0).mean(), include_groups=False).round(2),
            avg_pnl_pct=(g["profit_ratio"].mean() * 100).round(2),
            sum_pnl_pct=(g["profit_ratio"].sum() * 100).round(0),
            gross_win=(g.apply(lambda x: x.loc[x["profit_ratio"] > 0, "profit_abs"].sum(), include_groups=False)).round(0),
            gross_loss=(g.apply(lambda x: x.loc[x["profit_ratio"] <= 0, "profit_abs"].sum(), include_groups=False)).round(0),
            med_hold_h=g["hold_h"].median().round(1),
            max_hold_h=g["hold_h"].max().round(0),
            med_abs=g["profit_abs"].median().round(0),
        )
    )
    out["PF"] = (out["gross_win"] / out["gross_loss"].abs().replace(0, np.nan)).round(2)
    return out.sort_values("trades", ascending=False)


def main():
    zip_path = sys.argv[1]
    per_pair = "--per-pair" in sys.argv
    df = load_trades(zip_path)
    print(f"== {zip_path}: {len(df)} trades, {df['pair'].nunique()} pairs, "
          f"total profit ratio {df['profit_ratio'].sum()*100:.0f}% ==")
    ex = explode(df)
    print("\n-- per family (mixed-tag trades count once per contained family) --")
    print(agg(ex).to_string())
    print("\n-- per pair --")
    gp = df.groupby("pair")
    pair_tbl = pd.DataFrame(
        dict(
            trades=gp.size(),
            winrate=gp.apply(lambda x: (x["profit_ratio"] > 0).mean(), include_groups=False).round(2),
            sum_pnl_pct=(gp["profit_ratio"].sum() * 100).round(0),
            profit_abs=gp["profit_abs"].sum().round(0),
        )
    ).sort_values("trades", ascending=False)
    print(pair_tbl.to_string())
    if per_pair:
        print("\n-- family x pair counts --")
        print(pd.crosstab(ex["family"], ex["pair"]).to_string())
    print("\n-- exit reasons --")
    ge = df.groupby(df["exit_reason"].str.split("(").str[0].str.strip())
    print(pd.DataFrame(dict(trades=ge.size(), sum_pnl=(ge["profit_abs"].sum()).round(0))).to_string())


if __name__ == "__main__":
    main()
