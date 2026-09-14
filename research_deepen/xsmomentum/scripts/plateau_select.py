# -*- coding: utf-8 -*-
"""高原分析与参数选择（严格按 PREREGISTRATION.md §4.2 机械执行）：
- 高原 = IS LS 净 Sharpe >= 0.8*全网格 LS 最大 Sharpe 且 > 0 的格
- 高原成立: 格数 >= 5
- 选中参数: 高原内坐标分量中位数（归一化后）欧氏距离最小的格；并列取 IS Sharpe 高者
输出: results/plateau_selection.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
LB_GRID = [7, 14, 30, 60, 90]
SK_GRID = [0, 1]
H_GRID = [1, 5, 10]


def main():
    grid = pd.read_csv(HERE / "results" / "grid_is.csv")
    ls = grid[grid.portfolio == "LS"]
    best = ls.loc[ls.sharpe.idxmax()]
    thr = 0.8 * float(best.sharpe)
    plat = ls[(ls.sharpe >= thr) & (ls.sharpe > 0)].copy()
    n_plat = len(plat)

    med_lb = float(plat.lookback.median())
    med_sk = float(plat.skip.median())
    med_h = float(plat.hold.median())

    def norm_lb(x):  # 归一化到 [0,1]（按网格范围）
        return (LB_GRID.index(x) if x in LB_GRID else (np.interp(x, LB_GRID, range(len(LB_GRID))))) / (len(LB_GRID) - 1)
    def norm_sk(x):
        return SK_GRID.index(x) / (len(SK_GRID) - 1)
    def norm_h(x):
        return H_GRID.index(x) / (len(H_GRID) - 1)

    tgt = (norm_lb(med_lb) if med_lb in LB_GRID else np.interp(med_lb, LB_GRID, [norm_lb(v) for v in LB_GRID]),
           norm_sk(med_sk) if med_sk in SK_GRID else med_sk,
           norm_h(med_h) if med_h in H_GRID else med_h)
    dists = []
    for _, row in plat.iterrows():
        d = ((norm_lb(row.lookback) - tgt[0]) ** 2 + (norm_sk(row.skip) - tgt[1]) ** 2
             + (norm_h(row.hold) - tgt[2]) ** 2) ** 0.5
        dists.append((d, -row.sharpe, row.key))
    dists.sort()
    sel_key = dists[0][2]
    sel = plat[plat.key == sel_key].iloc[0]

    out = {
        "is_ls_max_sharpe": float(best.sharpe),
        "is_ls_max_key": str(best.key),
        "plateau_threshold_sharpe": thr,
        "plateau_cells": n_plat,
        "plateau_ok": bool(n_plat >= 5),
        "plateau_median_sharpe": float(plat.sharpe.median()),
        "plateau_member_keys": plat.key.tolist(),
        "plateau_members_sharpe": {r.key: float(r.sharpe) for _, r in plat.iterrows()},
        "coord_median": {"lookback": med_lb, "skip": med_sk, "hold": med_h},
        "selected": {"key": str(sel.key), "lookback": int(sel.lookback), "skip": int(sel.skip),
                     "hold": int(sel.hold), "is_sharpe": float(sel.sharpe),
                     "is_total": float(sel.total), "is_maxdd": float(sel.maxdd),
                     "is_pf": float(sel.pf), "is_hit": float(sel.hit)},
    }
    (HERE / "results" / "plateau_selection.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
