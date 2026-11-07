# -*- coding: utf-8 -*-
"""LV3 方向2: 多速 Donchian 混合 — S3h + S12h 双速各 50% 的混合袖估计

预声明于运行前(2026-11-07):
  输入: research_revive/slowa/sim_{S3h,S12h}_monthly.csv(同一模拟器、同一费口径,
        逐月 pnl_eq, sleeve 内部复利)。两袖月度再平衡到 50/50(线性装配近似):
        r_mix[m] = 0.5*(1+r3h[m]) + 0.5*(1+r12h[m]) - 1
  问题(任务书原文): 双速混合是否比单 12h 在 24-26 更平滑/更强?
  KEEP 判据(预注册): mix 的 24-26 平均年收益 >= S12h 单袖 且 全窗口(21-26)月频
        maxDD 比 S12h 改善 >= 3pp("更强且更平滑"同时成立; 只满足一边记 kill 并
        把装配信息移交 LV2, 不在本方向消耗新自由度)。
  附带披露: 两袖月度相关、21-23 窗口变化、freqtrade S12h 口径(+32.9/+18.3 于 25/26)
        高于模拟口径, 混合绝对值按保守口径读。
  多重检验: 1 个点(S3h+S12h 50/50), 无参数扫描。
"""
import pandas as pd

SLOWA = "/Users/caihaohan/Code/freqtrade-futures-lab/research_revive/slowa"
OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_lowvol/lv3"


def curve_stats(monthly: pd.Series, name):
    eq = (1 + monthly).cumprod()
    yearly = (eq.groupby(eq.index.year).last() / eq.groupby(eq.index.year).first() - 1) * 100
    dd = (eq / eq.cummax() - 1) * 100
    roll2 = (eq / eq.rolling(2).max() - 1) * 100  # 最差 2 月(≈30d)
    return dict(name=name,
                y21=yearly.get(2021), y22=yearly.get(2022), y23=yearly.get(2023),
                y24=yearly.get(2024), y25=yearly.get(2025), y26=yearly.get(2026),
                m2426=yearly.loc[2024:2026].mean(),
                m2123=yearly.loc[2021:2023].mean(),
                maxdd=dd.min(), worst2m=roll2.min(),
                mvol=monthly.std() * 100)


if __name__ == "__main__":
    m3 = pd.read_csv(f"{SLOWA}/sim_S3h_monthly.csv", parse_dates=["month"]).set_index("month")["pnl_eq"]
    m12 = pd.read_csv(f"{SLOWA}/sim_S12h_monthly.csv", parse_dates=["month"]).set_index("month")["pnl_eq"]
    idx = m3.index.intersection(m12.index)
    m3, m12 = m3.loc[idx], m12.loc[idx]
    mix = 0.5 * (1 + m3) + 0.5 * (1 + m12) - 1

    rows = [curve_stats(s, n) for s, n in [(m3, "S3h(=A模拟)"), (m12, "S12h"), (mix, "MIX_5050")]]
    res = pd.DataFrame(rows)
    for c in res.columns[1:]:
        res[c] = res[c].astype(float).round(1)
    res.to_csv(f"{OUT}/dualspeed_results.csv", index=False)
    print(res.to_string(index=False))
    corr_all = m3.corr(m12)
    corr_2426 = m3[m3.index >= "2024-01-01"].corr(m12[m12.index >= "2024-01-01"])
    print(f"\n月度相关 S3h~S12h: 全窗 {corr_all:.2f} | 24-26 {corr_2426:.2f}")
    # 逐年 24-26 对比细节
    for y in (2024, 2025, 2026):
        mm = mix[mix.index.year == y]
        a = m3[m3.index.year == y]; b = m12[m12.index.year == y]
        print(f"{y}: S3h {( (1+a).prod()-1)*100:+.1f}% | S12h {((1+b).prod()-1)*100:+.1f}% | mix {((1+mm).prod()-1)*100:+.1f}%")
