# -*- coding: utf-8 -*-
"""LV3 方向1: B-slow — 日频动量篮子(纯多, B 的门保留, 排名/调仓放日频)

预声明于运行前(2026-11-07, 见 lv3/report.md §1):
  结构(B 直译到日频):
    - 宇宙: 12 币 (BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI), 1h feather -> 日线
    - 因果性: 当日决策只用昨收(known = close.shift(1), 同 B 口径)
    - 动量: mom[t] = known[t] / known[t-N] - 1,  N ∈ {20, 30, 60}
    - regime 门(保留 B 终选值): BTC known > SMA100(known) x 1.03 (REGIME_TOLERANCE=-0.03)
    - 个币趋势过滤(保留 B 硬门): known > SMA50(known)
    - 滞回(B 结构): 入场 rank<=TOP_N, 留守 rank<=3*TOP_N (N=3 时 =9, 即 B 冻结值 EXIT_RANK_N=9)
    - TOP_N ∈ {3, 5}; 调仓: 日频 / 周频(周一决策)
    - 仓位: 每持有币 1/TOP_N 等权, 现金兜底; regime 关 = 全现金
    - 费用: cost = 0.1% x sum|目标权重 - 漂移权重|(单边换手 x 双边 taker 0.05%x2)
    - 无杠杆、无 funding(funding 门不保留: 任务书只声明保留 regime 门, 最小集)
  记账: 日 t 持仓于 t-1 收盘按目标权重建立; 日 t 收盘组合收益 = sum w[t-1]*r[t];
        换手在 t-1->t 决策点, 以漂移权重为基准。非决策日(周频)权重漂移不交易。
  网格(12 格, 全部报告, 不许挑): MOM{20,30,60} x TOP{3,5} x {daily,weekly}
  KEEP 判据(预注册): 存在格子同时满足
      2025 >= +15% 且 2026 >= +15% 且 2024 >= +30% 且 2022 >= -5% 且 maxDD <= 40%
    理由: B 袖 25/26 = +15/+8 是要修复的对象, B-slow 低波年不比 B 强就没有存在价值;
          2024 >= +30% 保住 B 领地不大塌; 2022 门关应近持平; maxDD 放宽(S4 单袖 <=50%)取更松一档。
"""
import numpy as np
import pandas as pd

DATA = "/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures"
OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_lowvol/lv3"
COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "LTC", "UNI"]
FEE = 0.001
START, END = "2021-01-01", "2026-11-07"


def daily_panel():
    cols = {}
    for c in COINS:
        df = pd.read_feather(f"{DATA}/{c}_USDT_USDT-1h-futures.feather")
        s = df.set_index("date")["close"].sort_index()
        cols[c] = s.resample("1D").last()
    P = pd.DataFrame(cols).sort_index()
    return P[(P.index >= START) & (P.index <= END)]


def membership(P, mom_n, top_n, rebalance):
    """日 t 的持有集(用 t-1 及更早收盘决定)。"""
    known = P.shift(1)
    mom = known / known.shift(mom_n) - 1
    btc = known["BTC"]
    ron = btc > btc.rolling(100).mean() * 1.03
    own = known > known.rolling(50).mean()
    rank = mom.rank(axis=1, ascending=False, method="first")
    gate = own & np.asarray(ron)[:, None]   # ron 行级门广播到 12 列
    enter_ok = (rank <= top_n) & gate
    stay_ok = (rank <= 3 * top_n) & gate

    out = []
    cur = frozenset()
    for i, dt in enumerate(P.index):
        if rebalance == "daily" or dt.day_of_week == 0:
            so = stay_ok.iloc[i]
            keep = {c for c in cur if bool(so[c])}
            free = top_n - len(keep)
            if free > 0:
                r = rank.iloc[i]
                eo = enter_ok.iloc[i]
                cands = [c for c in P.columns if bool(eo[c]) and c not in keep]
                cands.sort(key=lambda c: r[c])
                keep |= set(cands[:free])
            cur = frozenset(keep)
        out.append(cur)
    return out, ron


def run(P, mom_n, top_n, rebalance):
    held, ron = membership(P, mom_n, top_n, rebalance)
    rets = P.pct_change().fillna(0.0)

    eq = 1.0
    w_tgt = pd.Series(0.0, index=P.columns)   # 当前目标权重(决策日设定)
    eqs, turns = [], []
    cost_sum = 0.0
    for i in range(len(P)):
        r = rets.iloc[i]
        port_r = float((w_tgt * r).sum())
        # 日 i 收盘后: 漂移权重
        w_drift = w_tgt * (1 + r) / (1 + port_r)
        eq *= (1 + port_r)
        # 决策(日 i 收盘为日 i+1 设仓)
        j = i + 1
        turn = 0.0
        if j < len(P):
            if rebalance == "daily" or P.index[j].day_of_week == 0:
                w_new = pd.Series(0.0, index=P.columns)
                h = held[j]
                if h:
                    w_new[list(h)] = 1.0 / top_n
                turn = float((w_new - w_drift).abs().sum())
                cost_sum += FEE * turn
                eq -= FEE * turn
                w_tgt = w_new
            else:
                w_tgt = w_drift  # 无交易, 权重随漂移
        eqs.append(eq)
        turns.append(turn)

    curve = pd.Series(eqs, index=P.index)
    yearly = (curve.groupby(curve.index.year).last() / curve.groupby(curve.index.year).first() - 1) * 100
    dd = (curve / curve.cummax() - 1) * 100
    n_years = len(P) / 365.25
    return dict(
        mom_n=mom_n, top_n=top_n, reb=rebalance,
        y21=round(yearly.get(2021, 0), 1), y22=round(yearly.get(2022, 0), 1),
        y23=round(yearly.get(2023, 0), 1), y24=round(yearly.get(2024, 0), 1),
        y25=round(yearly.get(2025, 0), 1), y26=round(yearly.get(2026, 0), 1),
        total=round((curve.iloc[-1] / curve.iloc[0] - 1) * 100, 1),
        maxdd=round(dd.min(), 1),
        ann_turnover=round(float(np.mean(turns)) * 365.25 * 100, 0),
        fee_total=round(cost_sum * 100, 1),
        gate_open_pct=";".join(f"{int(y)}:{v:.0f}" for y, v in
                               (ron.groupby(P.index.year).mean() * 100).round(0).items()),
    )


if __name__ == "__main__":
    pd.set_option("display.width", 260)
    P = daily_panel()
    rows = [run(P, m, n, rb) for m in (20, 30, 60) for n in (3, 5) for rb in ("daily", "weekly")]
    res = pd.DataFrame(rows)
    res.to_csv(f"{OUT}/bslow_results.csv", index=False)
    print(res.drop(columns=["gate_open_pct"]).to_string(index=False))
    print("\nregime 门(BTC>SMA100x1.03) 每年开门占比% (两轴同门, 所有格子一致):")
    print(rows[0]["gate_open_pct"])
    # 开门窗内表现: 用 MOM30/TOP3/daily 的持有日条件收益作参考
    held, ron = membership(P, 30, 3, "daily")
    rets = P.pct_change().fillna(0.0)
    held_r = pd.Series([len(h) for h in held], index=P.index)
    port = (held_r > 0).astype(float)
    cond = {}
    for y in range(2021, 2027):
        m_y = (P.index.year == y) & (held_r > 0)
        r_day = pd.Series([float(sum(rets.iloc[i][c] for c in held[i]) / max(len(held[i]), 1) if held[i] else 0.0)
                           for i in range(len(P))], index=P.index)
        ann_open = (1 + r_day[m_y].mean()) ** 365 - 1 if m_y.sum() else 0
        cond[y] = f"{ann_open*100:.0f}%"
    print("\nMOM30/TOP3/daily 开门窗(有持仓日)年化等权收益参考:", cond)
