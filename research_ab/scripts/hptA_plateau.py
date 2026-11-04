"""Hyperopt-A plateau analysis: aggregate parameter-score surface from .fthypt
JSON-lines files (freqtrade 2026.8 format, one JSON object per line).

Usage: python research_ab/scripts/hptA_plateau.py <loss_tag> <fthypt> [<fthypt> ...]
Writes per-epoch CSV next to the report dir and prints:
  - top-N epochs table
  - top-20% (by loss) distribution of each parameter (plateau check)
  - full-sample distribution for contrast
"""
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

PARAMS = ["resample_hours", "signal_atr_mult", "stop_atr_mult",
          "cluster_stop_count", "cluster_window_h", "circuit_hours"]


def load(fthypt: Path) -> pd.DataFrame:
    rows = []
    with fthypt.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            pd_ = e.get("params_dict", {})
            rm = e.get("results_metrics", {})
            row = {
                "epoch": e.get("current_epoch"),
                "loss": e.get("loss"),
                "is_random": e.get("is_random"),
                "profit_total_pct": rm.get("profit_total") * 100 if rm.get("profit_total") is not None else None,
                "trades": rm.get("total_trades"),
                "max_dd_pct": rm.get("max_drawdown_account", rm.get("max_drawdown")) * 100
                if rm.get("max_drawdown_account", rm.get("max_drawdown")) is not None else None,
            }
            for p in PARAMS:
                row[p] = pd_.get(p)
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    tag = sys.argv[1]
    files = [Path(p) for p in sys.argv[2:]]
    df = pd.concat([load(f) for f in files], ignore_index=True)
    df = df.dropna(subset=["loss"]).sort_values("loss").reset_index(drop=True)
    df["rank"] = df.index + 1
    out_csv = Path(f"research_ab/results/hptA_epochs_{tag}.csv")
    df.to_csv(out_csv, index=False)

    n = len(df)
    print(f"== {tag}: {n} epochs from {[f.name for f in files]} -> {out_csv}")
    print("\n-- top 10 epochs (loss ascending; lower = better) --")
    cols = ["rank", "loss", "profit_total_pct", "max_dd_pct", "trades"] + PARAMS
    print(df.head(10)[cols].to_string(index=False))

    # Deduplicate identical parameter combos (re-asks of the same point and
    # inert-P2 permutations otherwise pollute the top slice).
    dups = df.duplicated(subset=PARAMS).sum()
    ddf = df.drop_duplicates(subset=PARAMS, keep="first").reset_index(drop=True)
    nd = len(ddf)
    print(f"\ndistinct combos: {nd} ({dups} duplicate-combo epochs removed) of 1440 in grid")

    top_frac = ddf.head(max(1, nd // 5))
    print(f"\n-- parameter distribution: top-20% ({len(top_frac)} distinct combos) vs all {nd} --")
    for p in PARAMS:
        c_top = Counter(top_frac[p])
        c_all = Counter(ddf[p])
        vals = sorted(c_all)
        top_share = ", ".join(f"{v}:{c_top.get(v, 0)}" for v in vals)
        all_share = ", ".join(
            f"{v}:{c_all[v]}({c_all[v]*100/nd:.0f}%)" for v in vals)
        # concentration: max share in top-20%
        mx = max(c_top.values()) / len(top_frac) if len(top_frac) else 0
        print(f"{p:>18}: top20%[{top_share}] maxshare={mx:.0%} | all[{all_share}]")

    print("\n-- mean loss by parameter value (surface scan, distinct combos) --")
    for p in PARAMS:
        g = ddf.groupby(p)["loss"].agg(["mean", "median", "count"]).sort_index()
        print(f"\n{p}:")
        print(g.to_string())

    # cross-tab: the two entry-side knobs (the plateau that matters most)
    print("\n-- mean loss: resample_hours x signal_atr_mult (distinct combos) --")
    print(ddf.pivot_table(index="resample_hours", columns="signal_atr_mult",
                          values="loss", aggfunc="mean").round(3).to_string())
    print("\n-- mean loss: resample_hours x stop_atr_mult --")
    print(ddf.pivot_table(index="resample_hours", columns="stop_atr_mult",
                          values="loss", aggfunc="mean").round(3).to_string())


if __name__ == "__main__":
    main()
