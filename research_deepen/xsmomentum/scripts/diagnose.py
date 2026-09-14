# -*- coding: utf-8 -*-
"""报告诊断：选中参数的 XS 组合动态。
- 逐月：LS 净收益、LO、SO、市场(宇宙等权)收益、平均合格币数
- LS 月收益 vs 市场月收益的相关（beta 诊断）
输出: results/diagnostics.json + results/monthly_table.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import xs_engine as xe

HERE = Path(__file__).resolve().parents[1]


def main():
    uni = json.load(open(HERE / "universe_frozen_v2.json", encoding="utf-8"))
    bases = [xe.pair_to_base(u["symbol"]) for u in uni["top40"]]
    close, _ = xe.load_close_volume(bases)
    tz = close.index.tz
    close = close[close.index < pd.Timestamp("2024-01-01", tz=tz)]
    funding, _ = xe.load_funding_daily(bases, close.index)
    ret = close.pct_change()

    sel = json.load(open(HERE / "results" / "plateau_selection.json", encoding="utf-8"))["selected"]
    lb, sk, h = sel["lookback"], sel["skip"], sel["hold"]
    mom = xe.momentum(close, lb, sk)

    # 合格币数（再平衡日）
    elig_n = mom.notna().sum(axis=1)
    print("eligible coins: min=%d median=%d max=%d" % (elig_n.min(), elig_n.median(), elig_n.max()))

    series = {}
    for pf_ in ["LS", "LO", "SO"]:
        r = xe.simulate(close, ret, mom, funding, pf_, h, "2021-01-01", "2024-01-01").daily
        series[pf_] = r
    df = pd.DataFrame(series)
    mkt = ret.mean(axis=1)  # 宇宙等权(可用币均值)日收益
    df["MKT"] = mkt
    monthly = (1.0 + df.fillna(0.0)).resample("ME").prod() - 1.0
    monthly.index = monthly.index.tz_localize(None)
    monthly.to_csv(HERE / "results" / "monthly_table.csv")

    corr_ls_mkt = float(monthly["LS"].corr(monthly["MKT"]))
    corr_lo_mkt = float(monthly["LO"].corr(monthly["MKT"]))
    out = {
        "eligible_min": int(elig_n.min()), "eligible_median": float(elig_n.median()),
        "eligible_max": int(elig_n.max()),
        "monthly_corr_LS_vs_MKT_2021_2023": corr_ls_mkt,
        "monthly_corr_LO_vs_MKT_2021_2023": corr_lo_mkt,
        "ls_monthly_2023_sum_log": float(np.log1p(monthly["LS"]["2023"]).sum()),
        "mkt_monthly_2023": {str(k.date()): round(v, 4) for k, v in monthly["MKT"]["2023"].items()},
        "ls_monthly_2023": {str(k.date()): round(v, 4) for k, v in monthly["LS"]["2023"].items()},
    }
    (HERE / "results" / "diagnostics.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if not isinstance(v, dict)}, indent=2))
    print("2023 monthly MKT vs LS:")
    print(pd.DataFrame({"MKT": monthly["MKT"]["2023"], "LS": monthly["LS"]["2023"]}).round(4).to_string())


if __name__ == "__main__":
    main()
