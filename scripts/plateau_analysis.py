#!/usr/bin/env python
"""Parameter-plateau analysis from freqtrade hyperopt results (.fthypt, JSON lines).

Reads all epochs, reports per-parameter distributions over:
  - all epochs
  - profitable epochs only (profit_total > 0)
A healthy strategy has a *plateau*: many profitable epochs spread over a range
of parameter values, not a single spike.

Usage: python scripts/plateau_analysis.py STRATEGY [fthypt_file]
Writes user_data/reports/plateau_<STRATEGY>.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "user_data/reports"


def main():
    strategy = sys.argv[1]
    if len(sys.argv) > 2:
        f = Path(sys.argv[2])
    else:
        files = sorted((ROOT / "user_data/hyperopt_results").glob(f"strategy_{strategy}_*.fthypt"))
        f = files[-1]

    recs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    rows = []
    for r in recs:
        if not r.get("params_dict"):
            continue
        row = dict(r["params_dict"])
        row["profit_total"] = r.get("results_metrics", {}).get("profit_total")
        row["trades"] = r.get("results_metrics", {}).get("total_trades")
        row["max_dd"] = r.get("results_metrics", {}).get("max_drawdown_account")
        row["loss"] = r.get("loss")
        rows.append(row)
    df = pd.DataFrame(rows)
    params = [c for c in df.columns if c not in ("profit_total", "trades", "max_dd", "loss")]
    prof = df[df["profit_total"] > 0]

    lines = [
        f"# 参数高原分析: {strategy}", "",
        f"- 数据: `{f.name}`（{len(df)} epochs，SharpeHyperOptLoss，seed=42，仅样本内 2021-2022）",
        f"- 盈利 epochs: **{len(prof)}/{len(df)}**（profit_total > 0）",
        "",
        "## 盈利 epochs 的参数分布（高原证据）", "",
    ]
    if len(prof) == 0:
        lines.append("无盈利 epoch —— 不存在参数高原，该策略家族应判失败。")
    else:
        desc = prof[params + ["profit_total", "trades"]].describe(
            percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).T
        lines.append(desc.to_markdown())
        lines += ["", "## 参数与收益的相关性（|corr| 接近 1 = 单点敏感，接近 0 = 平坦高原）", ""]
        corr = prof[params + ["profit_total"]].corr()["profit_total"].drop("profit_total")
        lines.append(corr.to_markdown())
        lines += [
            "", "## 候选高原参数（盈利 epochs 的中位数）", "",
        ]
        med = prof[params].median().round(4)
        lines.append(med.to_markdown())
        lines += [
            "", f"盈利 epochs 收益范围: {prof['profit_total'].min()*100:.1f}% ~ {prof['profit_total'].max()*100:.1f}%，"
            f"交易数中位数 {prof['trades'].median():.0f}", "",
        ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"plateau_{strategy}.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines[:14]))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
