# -*- coding: utf-8 -*-
"""
WS2 — AB 权重 × 回收系数系统扫描（按时期 / 市场形势分解 + 块自助法蒙特卡洛）

数据（窗口 2021-01-02 .. 2026-09-12 的日收益，共 2080 个收益日）:
  rA = user_data/logs/mtm_daily_A3.csv  (sleeve A = OPT4, 3 币) 的 pct_change
  rB = user_data/logs/mtm_daily_B3.csv  (sleeve B = OPT2, 3 币) 的 pct_change
  BTC 1h: user_data/data/binance/futures/BTC_USDT_USDT-1h-futures.feather

公开信号（严格因果，对齐方式见报告）:
  日线 D 的收盘 C(D) = 当日 23:00 UTC 起 1h bar 的收盘（= 次日 00:00 UTC 价）。
  MTM 行 t 的权益盖戳 00:00 UTC(t)，故行 t 的收益覆盖 UTC 日 t-1 的交易。
  => 行 t 的信号必须在 (t-1) 00:00 UTC 时刻已知：最后一张完整日线是 D=t-2。
  s_t = 1  iff  C(t-2) < SMA100(C)(t-2)     [主口径, shift=2]
  变体: shift=1（任务字面式：C(t-1)）, shift=3（多滞后一天的反应下界）。
  RV30_t = BTC 日对数收益截至 D=t-2 的 30d 年化已实现波动（同口径因果）。

组合: r_p(t) = (1-wB)*rA + wB*[(1-s_t)*rB + s_t*f*rA],  wB∈{.20,.25,.30,.36,.40,.45,.50}, f∈{0,.5,1}

MC: 对 (rA, rB, s) 三元组同日联合做块自助（块长 30d, 2000 次, seed=20261103），
    每条路径算 30d 滚动 DD 的最深值 -> p5（=p95 深度分界）与 P(触 -20% 线)。

运行: cd D:/Code/AIQuant/freqtrade-futures-lab
      PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe research_ab/ws2_analysis.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

ROOT = Path(__file__).resolve().parents[1]

SEED = 20261103
N_MC = 2000
BLOCK = 30
DD_LINE = -0.20
WB_GRID = [0.20, 0.25, 0.30, 0.36, 0.40, 0.45, 0.50]
F_GRID = [0.0, 0.5, 1.0]
ANN = 365.25  # crypto 全年无休


def hr(title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


# ---------------------------------------------------------------- 1. 加载
a_eq = pd.read_csv(ROOT / "user_data/logs/mtm_daily_A3.csv", index_col=0, parse_dates=True)["eq_A3"]
b_eq = pd.read_csv(ROOT / "user_data/logs/mtm_daily_B3.csv", index_col=0, parse_dates=True)["eq_B3"]
assert (a_eq.index == b_eq.index).all(), "A/B 日期索引不一致"
assert a_eq.index.is_monotonic_increasing and not a_eq.index.duplicated().any()
assert (np.diff(a_eq.index.values) == np.timedelta64(1, "D")).all(), "MTM 日期非连续"

rA = a_eq.pct_change().iloc[1:]
rB = b_eq.pct_change().iloc[1:]
idx = rA.index
n = len(rA)
vA, vB = rA.values, rB.values
flatB = vB == 0.0

btc = pd.read_feather(ROOT / "user_data/data/binance/futures/BTC_USDT_USDT-1h-futures.feather")
btc["day"] = btc["date"].dt.floor("D")
bars_per_day = btc.groupby("day").size()
C = btc.groupby("day")["close"].last().loc[:"2026-09-13"]  # 剔除末尾不完整日
anom = bars_per_day[bars_per_day != 24]
sma100 = C.rolling(100).mean()
bear = (C < sma100).where(sma100.notna())  # 索引 = 日线标签 D, 值在 (D+1) 00:00 UTC 才可知; 前99日未定义
logret = np.log(C / C.shift(1))
rv30 = logret.rolling(30).std() * np.sqrt(ANN)


def shifted(series, back):
    """行 t 取 series 在日线标签 (t-back) 处的值。"""
    vals = series.reindex(idx - pd.Timedelta(days=back))
    assert not vals.isna().any(), f"信号 shift={back} 存在未定义值"
    return vals.values.astype(bool)


s_variants = {back: shifted(bear, back) for back in (0, 1, 2, 3)}
assert not pd.isna(rv30.reindex(idx - pd.Timedelta(days=2))).any()
rv = rv30.reindex(idx - pd.Timedelta(days=2)).values.astype(float)
s_main = s_variants[2].astype(float)

hr(f"0. 数据概况  |  收益日 {idx[0].date()} .. {idx[-1].date()}  n={n}  |  BTC 1h {btc['date'].min()} .. {btc['date'].max()}")
print(f"BTC 非完整日线(≠24根1h bar)天数: {len(anom)}  {list(anom.items())[:5]}")
print(f"corr(rA, rB) = {np.corrcoef(vA, vB)[0,1]:.3f}   (上轮结论 0.453)")
print(f"rA: 总收益 {a_eq.iloc[-1]/a_eq.iloc[0]-1:+.1%}  日波动 {vA.std()*100:.2f}%   rB: 总收益 {b_eq.iloc[-1]/b_eq.iloc[0]-1:+.1%}  日波动 {vB.std()*100:.2f}%")
print(f"B 零收益日(空仓近似): {flatB.sum()}/{n} = {flatB.mean():.1%}   (上轮'全程54%天空仓'口径略异, 对照)")

# ---------------------------------------------------------------- 2. 信号验证
hr("1. 信号验证: s(shift) vs B 零收益日 一致率  [主口径 shift=2 = 行t收益区间起点最后一张完整日线]")
rows = []
for back, sv in s_variants.items():
    agree = (sv == flatB)
    rows.append({
        "shift": back,
        "含义": {0: "C(t) 区间末端(未来,仅诊断)", 1: "C(t-1) 任务字面式", 2: "C(t-2) 严格因果[主]", 3: "C(t-3) 多滞后一天"}[back],
        "s=1天数": int(sv.sum()), "s=1占比": f"{sv.mean():.1%}",
        "与B空仓一致率": f"{agree.mean():.1%}",
        "s=1且B空仓": int((sv & flatB).sum()), "s=1但B持仓": int((sv & ~flatB).sum()),
        "s=0但B空仓": int((~sv & flatB).sum()), "s=0且B持仓": int((~sv & ~flatB).sum()),
    })
print(pd.DataFrame(rows).to_string(index=False))
s = s_variants[2]
print("\n主口径 s_t 分年熊态占比与分段:")
yearly_bear = pd.Series(s.astype(float), index=idx).groupby(idx.year).mean()
print(yearly_bear.map(lambda x: f"{x:.1%}").to_string())


def longest_run(mask):
    best = cur = 0
    best_end = -1
    for i, v in enumerate(mask):
        cur = cur + 1 if v else 0
        if cur > best:
            best, best_end = cur, i
    return best, idx[best_end - best + 1].date(), idx[best_end].date()


for name, mask in (("s=1 熊态", s), ("s=0 牛态", ~s)):
    L, d0, d1 = longest_run(mask)
    print(f"最长连续 {name}: {L} 天  {d0} .. {d1}")

# ---------------------------------------------------------------- 3. 组合网格 + 指标
configs = [(f, wB) for f in F_GRID for wB in WB_GRID]  # 21 个


def metrics(r, index, window=30):
    r = np.asarray(r, dtype=float)
    eq = np.cumprod(1.0 + r)
    span = (index[-1] - index[0]).days
    total = eq[-1] - 1.0
    cagr = eq[-1] ** (ANN / span) - 1.0
    sharpe = r.mean() / (r.std(ddof=1) * np.sqrt(1.0 / ANN)) if r.std(ddof=1) > 0 else np.nan
    peak = np.maximum.accumulate(eq)
    maxdd = (eq / peak - 1.0).min()
    rollmax = sliding_window_view(eq, window).max(axis=1)
    dd30 = eq[window - 1:] / rollmax - 1.0
    return {"total": total, "cagr": cagr, "sharpe": sharpe, "maxdd": maxdd,
            "dd30": dd30.min(), "touch20": int((dd30 <= DD_LINE).sum())}


rp = {}
for f, wB in configs:
    rp[(f, wB)] = (1 - wB) * vA + wB * ((1 - s_main) * vB + s_main * f * vA)

masks = {"21-26 全窗口": np.ones(n, dtype=bool),
         "21-23 池内": np.asarray(idx.year <= 2023),
         "24-26 披露窗": np.asarray(idx.year >= 2024)}

hr("2. 主表 — 全窗口 2021-01-02..2026-09-12 (21 配置 + A/B 单独)")
head = ["配置", "总收益", "CAGR", "Sharpe", "从峰maxDD", "最深30d滚动DD", "触-20%线天数"]
table = []
for name, r in [("A 100%", vA), ("B 100%", vB)] + [(f"f={f:g} wB={wB:.2f}", rp[(f, wB)]) for f, wB in configs]:
    m = metrics(r, idx)
    table.append([name, f"{m['total']:+.1%}", f"{m['cagr']:+.1%}", f"{m['sharpe']:.2f}",
                  f"{m['maxdd']:.1%}", f"{m['dd30']:.1%}", m["touch20"]])
print(pd.DataFrame(table, columns=head).to_string(index=False))

hr("3. 分段表 — 21-23 池内 vs 24-26 披露窗 (各段独立重定基)")
for seg, msk in list(masks.items())[1:]:
    print(f"\n--- {seg}  ({idx[msk][0].date()} .. {idx[msk][-1].date()}, {msk.sum()} 收益日) ---")
    table = []
    for name, r in [("A 100%", vA), ("B 100%", vB)] + [(f"f={f:g} wB={wB:.2f}", rp[(f, wB)]) for f, wB in configs]:
        m = metrics(np.asarray(r)[msk], idx[msk])
        table.append([name, f"{m['total']:+.1%}", f"{m['cagr']:+.1%}", f"{m['sharpe']:.2f}",
                      f"{m['maxdd']:.1%}", f"{m['dd30']:.1%}", m["touch20"]])
    print(pd.DataFrame(table, columns=head).to_string(index=False))

hr("4. 分年收益表 (全部 21 配置, 2026 截至 09-12)")
years = sorted(idx.year.unique())
ycols = []
for name, r in [("A", vA), ("B", vB)]:
    ycols.append([name] + [f"{np.prod(1 + r[np.asarray(idx.year == y)]) - 1:+.1%}" for y in years])
for f, wB in configs:
    r = rp[(f, wB)]
    ycols.append([f"f={f:g} wB={wB:.2f}"] + [f"{np.prod(1 + r[np.asarray(idx.year == y)]) - 1:+.1%}" for y in years])
print(pd.DataFrame(ycols, columns=["配置"] + [str(y) for y in years]).to_string(index=False))

# ---------------------------------------------------------------- 4. 条件矩阵
hr("5. 条件矩阵 — s_t(牛/熊) × RV30(低/高, 全窗口中位数二分)  [均为因果条件: 信号用 t-2 及以前]")
med = np.median(rv)
cells = {
    "牛市×低波": (s_main == 0) & (rv <= med),
    "牛市×高波": (s_main == 0) & (rv > med),
    "熊态×低波": (s_main == 1) & (rv <= med),
    "熊态×高波": (s_main == 1) & (rv > med),
}
print("四形势天数: " + "  ".join(f"{k}={v.sum()}({v.mean():.0%})" for k, v in cells.items()))
print(f"RV30 中位数 = {med:.1%} (年化); 高波占比 {np.mean(rv > med):.0%}")

rows_ret, rows_vol = [], []
for name, r in [("A 100%", vA), ("B 100%", vB)] + [(f"f={f:g} wB={wB:.2f}", rp[(f, wB)]) for f, wB in configs]:
    r = np.asarray(r)
    rows_ret.append([name] + [f"{r[m].mean() * ANN:+.0%}" if m.sum() else "-" for m in cells.values()])
    rows_vol.append([name] + [f"{r[m].std() * np.sqrt(ANN):.0%}" if m.sum() else "-" for m in cells.values()])
print("\n条件年化收益 (日均×365.25, %):")
print(pd.DataFrame(rows_ret, columns=["配置"] + list(cells)).to_string(index=False))
print("\n条件年化波动 (日std×√365.25, %):")
print(pd.DataFrame(rows_vol, columns=["配置"] + list(cells)).to_string(index=False))

# 对齐敏感性: 任务字面式(shift=1) 与 滞后式(shift=3) 下关键指标的偏移
hr("5b. 对齐敏感性 — 主口径 shift=2 vs 任务字面 shift=1 vs 滞后 shift=3 (全窗口 CAGR / Sharpe / 最深30dDD)")
sens = []
for back in (1, 2, 3):
    sv = s_variants[back].astype(float)
    sub = []
    for f, wB in configs:
        m = metrics((1 - wB) * vA + wB * ((1 - sv) * vB + sv * f * vA), idx)
        sub.append(f"{m['cagr']:+.0%}/{m['sharpe']:.2f}/{m['dd30']:.0%}")
    sens.append(sub)
df_sens = pd.DataFrame({"配置": [f"f={f:g} wB={wB:.2f}" for f, wB in configs],
                        "shift=1": sens[0], "shift=2[主]": sens[1], "shift=3": sens[2]})
print(df_sens.to_string(index=False))

# ---------------------------------------------------------------- 5. 蒙特卡洛
hr("6. 蒙特卡洛 — 块自助(块长30d, 2000次, seed=20261103), 联合重采样 (rA,rB,s)")
rng = np.random.default_rng(SEED)
nblk = int(np.ceil(n / BLOCK))
cfgA0 = np.array([1 - wB for f, wB in configs])          # 常数项 (f=0 部分)
cfgA1 = np.array([wB * f for f, wB in configs])          # s_t 系数
cfgB = np.array([wB for f, wB in configs])               # (1-s_t) 系数
n_cfg = len(configs) + 2                                 # + A 100% / B 100% 参考
min30 = np.zeros((N_MC, n_cfg))
touch = np.zeros((N_MC, n_cfg), dtype=bool)
ofs = np.arange(BLOCK)
for it in range(N_MC):
    st = rng.integers(0, n - BLOCK + 1, nblk)
    pos = (st[:, None] + ofs[None, :]).ravel()[:n]
    a_s, b_s, s_s = vA[pos], vB[pos], s_main[pos]
    r_cfg = (cfgA0[None, :] + cfgA1[None, :] * s_s[:, None]) * a_s[:, None] \
        + (cfgB[None, :] * (1 - s_s)[:, None]) * b_s[:, None]
    r_all = np.hstack([r_cfg, a_s[:, None], b_s[:, None]])   # 末两列 = A/B 单独
    eq_all = np.cumprod(1.0 + r_all, axis=0)
    rollmax = sliding_window_view(eq_all, BLOCK, axis=0).max(axis=-1)  # numpy2: 窗口轴在末尾
    dd = eq_all[BLOCK - 1:] / rollmax - 1.0
    min30[it] = dd.min(axis=0)
    touch[it] = (dd <= DD_LINE).any(axis=0)
p95 = np.percentile(min30, 5, axis=0)
med_mc = np.percentile(min30, 50, axis=0)
ptouch = touch.mean(axis=0)

print("注: MC p95 深度 = 每条路径最深 30d 滚动 DD 的第 5 百分位(负值越深越差); 余量 = p95 - (-20%)")
table = []
names = [f"f={f:g} wB={wB:.2f}" for f, wB in configs] + ["A 100%", "B 100%"]
hist_dd30 = [metrics(rp[(f, wB)], idx)["dd30"] for f, wB in configs] + [metrics(vA, idx)["dd30"], metrics(vB, idx)["dd30"]]
for j, nm in enumerate(names):
    table.append([nm, f"{hist_dd30[j]:.1%}", f"{med_mc[j]:.1%}", f"{p95[j]:.1%}",
                  f"{p95[j] - DD_LINE:+.1%}", f"{ptouch[j]:.1%}"])
print(pd.DataFrame(table, columns=["配置", "历史最深30dDD", "MC中位30dDD", "MC p95 30dDD", "p95距-20%余量", "P(触-20%)"]).to_string(index=False))

hr("完成. 全部表格由 research_ab/ws2_analysis.py 生成 (可重跑, 固定 seed)")
