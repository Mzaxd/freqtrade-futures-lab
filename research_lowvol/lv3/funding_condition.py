# -*- coding: utf-8 -*-
"""LV3 方向4: funding 条件化(谨慎) — funding 极端作为 SlowA/A 入场回避的信号级增益

预声明于运行前(2026-11-07):
  数据: BTC/ETH/SOL funding feather(8h 结算, 2020-07..2026-11 全覆盖, 先查覆盖=已通过)。
  因果口径: 时刻 t 可知 = 最后一次结算时刻 s <= t 的已结算 rate(结算即知, 无前视)。
  阈值(任务书给定点, 单点不扫): |rate| > 0.001 (0.1%/8h) = 极端。
  两个变体(各 1 点, 共 2 点/袖):
    (a) 同侧拥挤: 做多入场时 rate > +0.1% 阻断, 做空入场时 rate < -0.1% 阻断
    (b) 任意极端: |rate| > 0.1% 即阻断(不分方向)
  检验对象: research_revive/slowa/sim_{S12h,S3h}_trades.csv(SlowA 代理 / A 代理;
    模拟 PnL 不含 funding 成本 -> 无机械混杂, 纯"状态预测交易结局"检验, 披露)。
  度量: 被阻交易的 pnl_eq 分布(均值/中位/胜率) vs 其余; 逐年"回避增益"pp =
        -sum(blocked pnl_eq)/年初始权益; 与 2pp/年门槛比较。
  KILL 判据: 两个袖的年均增益均 < 2pp/年 -> 杀; 或被阻样本 <5 笔(无统计意义)。
  正交性: 不开仓收 funding(非 carry); 不加市场门/环境切换; 只在既有趋势系统的
    入场时刻做回避, 与"funding 收割"(C0 关)不同族。
"""
import numpy as np
import pandas as pd

DATA = "/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures"
SLOWA = "/Users/caihaohan/Code/freqtrade-futures-lab/research_revive/slowa"
OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_lowvol/lv3"
THR = 0.001
YEARS = list(range(2021, 2027))


def funding_state(coin):
    f = pd.read_feather(f"{DATA}/{coin}_USDT_USDT-1h-funding_rate.feather")
    f["date"] = pd.to_datetime(f["date"], utc=True)
    f = f.set_index("date").sort_index()["funding_rate"]
    return f


def attach(trades):
    """给每笔交易挂上入场时刻的已结算 funding rate(该币)。"""
    out = []
    for c in ("BTC", "ETH", "SOL"):
        fr = funding_state(c)
        t = trades[trades["coin"] == c].copy()
        ts = pd.to_datetime(t["open"], utc=True)
        fr_i = fr.index.astype("int64").to_numpy()
        ts_i = ts.astype("int64").to_numpy()
        idx = np.searchsorted(fr_i, ts_i, side="right") - 1
        t["fr_entry"] = fr.iloc[idx].values
        t["fr_time"] = fr.index[idx]
        t["lag_h"] = (ts - t["fr_time"]).dt.total_seconds() / 3600
        out.append(t)
    return pd.concat(out).sort_values("open")


def evaluate(tag, tr):
    eq_end = tr.sort_values("close")["eq_after"].iloc[-1]
    rows = []
    for variant in ("same_side", "any_extreme"):
        if variant == "same_side":
            blocked = (tr["side"] == 1) & (tr["fr_entry"] > THR) | (tr["side"] == -1) & (tr["fr_entry"] < -THR)
        else:
            blocked = tr["fr_entry"].abs() > THR
        b = tr[blocked]; o = tr[~blocked]
        # 逐年增益 pp = -sum(blocked pnl_eq)/eq_start(年)
        eq_start = 1.0
        gains = {}
        for y in YEARS:
            by = b[b["year"] == y]
            gains[y] = round(-by["pnl_eq"].sum() / eq_start * 100, 1)
            last_prev = tr[tr["year"] < y]["eq_after"]
            eq_start = last_prev.iloc[-1] if len(last_prev) else 1.0
        rows.append(dict(
            sleeve=tag, variant=variant, n_blocked=int(blocked.sum()), n_total=len(tr),
            blk_mean_bp=round(b["pnl_eq"].mean() * 1e4, 0) if len(b) else np.nan,
            blk_win=round(100 * (b["pnl_eq"] > 0).mean(), 0) if len(b) else np.nan,
            oth_mean_bp=round(o["pnl_eq"].mean() * 1e4, 0),
            gain_by_year=str(gains),
            gain_mean_pp=round(float(np.mean(list(gains.values()))), 2),
        ))
    return rows


if __name__ == "__main__":
    pd.set_option("display.width", 260)
    # funding 覆盖与极端占比
    for c in ("BTC", "ETH", "SOL"):
        fr = funding_state(c)
        fr = fr[fr.index.year >= 2021]
        print(f"{c}: 结算数 {len(fr)}, |rate|>0.1% 占比 {100*(fr.abs()>THR).mean():.1f}%, "
              f"rate>0.1% 占比 {100*(fr>THR).mean():.1f}%, rate<-0.1% 占比 {100*(fr<-THR).mean():.1f}%")
    rows = []
    for sleeve, path in [("SlowA_S12h", f"{SLOWA}/sim_S12h_trades.csv"),
                         ("A_S3h", f"{SLOWA}/sim_S3h_trades.csv")]:
        tr = pd.read_csv(path)
        tr = attach(tr)
        print(f"\n== {sleeve}: 入场时刻 funding 可得 {tr['fr_entry'].notna().mean()*100:.0f}%, "
              f"中位 lag {tr['lag_h'].median():.0f}h ==")
        rows += evaluate(sleeve, tr)
    res = pd.DataFrame(rows)
    res.to_csv(f"{OUT}/funding_condition_results.csv", index=False)
    print()
    print(res.to_string(index=False))
