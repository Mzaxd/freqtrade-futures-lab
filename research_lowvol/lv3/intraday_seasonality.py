# -*- coding: utf-8 -*-
"""LV3 方向3: 日内季节性(快杀) — 小时-of-day 收益 by year, 3 币 1h

预声明于运行前(2026-11-07):
  数据: BTC/ETH/SOL 1h close-to-close, r[t] = close[t]/close[t-1]-1, 归属=收盘 bar 的小时(UTC)。
  稳定性定义(任务书底线 ≥3 年同号, 但 3/6 同号在 72 格下期望假阳性 ~8 格, 太弱):
    主判据 = 同一 hour 在 3 币中各有 >=5/6 年同号 且 全部同向 且 三币六年均值的
    绝对值都 >= 3bp/小时 —— 跨币同向确认后才算"稳定模式"。
  经济性现实检验: 任何小时轮动策略至少每天一次双边换仓, taker 成本 ~10bp/天,
    即候选小时效应须 ~>10bp/天才够付成本。
  KILL 判据: 无任何 hour 通过主判据。
  多重检验: 24 hour x 3 币 = 72 格描述统计(全部输出, 不挑选)。
"""
import numpy as np
import pandas as pd

DATA = "/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures"
OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_lowvol/lv3"
YEARS = list(range(2021, 2027))


def hourly(coin):
    df = pd.read_feather(f"{DATA}/{coin}_USDT_USDT-1h-futures.feather")
    s = df.set_index("date")["close"].sort_index()
    r = s.pct_change()
    r = r[(r.index.year >= 2021)]
    tbl = r.groupby([r.index.year, r.index.hour]).mean().unstack(0) * 10000  # bp
    return tbl  # index=hour, columns=year


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    tables = {c: hourly(c) for c in ("BTC", "ETH", "SOL")}
    summary = {}
    for c, t in tables.items():
        rows = {}
        for h in range(24):
            row = t.loc[h]
            pos, neg = int((row > 0).sum()), int((row < 0).sum())
            same = max(pos, neg)
            direction = "+" if pos >= neg else "-"
            rows[h] = dict(same_sign_years=same, direction=direction,
                           mean_all_bp=round(row.mean(), 1),
                           min_year_bp=round(row.min(), 1), max_year_bp=round(row.max(), 1))
        summary[c] = pd.DataFrame(rows).T
        summary[c].to_csv(f"{OUT}/seasonality_{c}.csv")
        print(f"\n== {c} (小时均值 bp, 21-26) ==")
        print(summary[c].to_string())

    # 主判据
    print("\n== 主判据: 3 币同 hour 均 >=5/6 同号 + 同向 + |六年均值|>=3bp ==")
    passed = []
    for h in range(24):
        ok = True
        signs = []
        for c in ("BTC", "ETH", "SOL"):
            r = summary[c].loc[h]
            if not (r["same_sign_years"] >= 5 and abs(r["mean_all_bp"]) >= 3.0):
                ok = False
                break
            signs.append(r["direction"])
        if ok and len(set(signs)) == 1:
            passed.append((h, signs))
    print("通过判据的 hour:", passed if passed else "无")
    # 任务书底线(>=3/6)计数, 仅作披露
    n3 = sum(1 for c in ("BTC", "ETH", "SOL") for h in range(24) if summary[c].loc[h]["same_sign_years"] >= 3)
    n5 = sum(1 for c in ("BTC", "ETH", "SOL") for h in range(24) if summary[c].loc[h]["same_sign_years"] >= 5)
    print(f"披露: >=3/6 同号的格子 {n3}/72 (随机期望 ~66), >=5/6 的 {n5}/72 (随机期望 ~8)")
