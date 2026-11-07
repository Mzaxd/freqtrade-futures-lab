# -*- coding: utf-8 -*-
"""research_lowvol wave2 — 真实曲线装配验证(charter S1-S4)

用 LV1 真实回测曲线(SlowA_r3 / r2,非 ×k 近似)+ LV2 已校验袖曲线,
对冠军候选 cell40(B 30% + SlowA_r3 70%)做精确装配:
- 再平衡频率敏感性 {日, 月, 季, 年}
- 对照:cell40_r2、cell49(A_vt30/B_vt30/SlowA_r3 40)、权重 ±5 敏感性
- MC 块自助(30d 块, 2000 路, seed=20261107)→ dd30 p95 / P(年<+22%) / P(年<0)
只读既有数据;产物 CSV 同目录。口径:年收益=日历年内日收益复利;dd30=30 日滚动最差。
强平数=各袖回测实测(装配为线性近似,两袖各自 0 强平)。
"""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('/Users/caihaohan/Code/freqtrade-futures-lab')
BT = ROOT / 'user_data/backtest_results'
OUT = ROOT / 'research_lowvol/wave2'
OUT.mkdir(parents=True, exist_ok=True)
SEED = 20261107


def sleeve_daily_from_zip(zname: str, init: float, col: str) -> pd.Series:
    """逐笔重建日权益(close_date+profit_abs);末端锚定 final_balance。"""
    with zipfile.ZipFile(BT / zname) as z:
        j = [n for n in z.namelist() if n.endswith('.json') and 'config' not in n][0]
        strat = json.loads(z.read(j))['strategy']
        key = list(strat.keys())[0]
        trades = strat[key]['trades']
        final = float(strat[key]['final_balance'])
    df = pd.DataFrame([{'d': t['close_date'][:10], 'p': t['profit_abs']} for t in trades])
    day = df.groupby('d')['p'].sum().sort_index()
    idx = pd.date_range(day.index.min(), day.index.max(), freq='D')
    # 先 reindex 到完整日历(非交易日 PnL=0),再 cumsum —— 顺序反了会把权益锯齿化
    eq = init + day.reindex(idx.strftime('%Y-%m-%d')).fillna(0).cumsum().values
    eq[-1] = final  # 修 wallet feather 末端缺 force_exit 的已知坑
    s = pd.Series(eq, index=idx, name=col)
    assert abs(s.iloc[0] - init) / init < 0.05, f'{col} 初始偏离'
    return s


def yearly_returns(rp: pd.Series) -> dict:
    eq = (1 + rp).cumprod()
    ye = eq.resample('YE').last()
    prev = np.r_[1.0, ye.values[:-1]]
    return {int(idx.year): round((v / p - 1) * 100, 1) for idx, v, p in zip(ye.index, ye.values, prev)}


def blend(daily_ret: pd.DataFrame, weights: dict, rebal: str) -> pd.Series:
    """多袖日收益按目标权重装配;rebal ∈ {D,M,Q,A}。"""
    cols = list(weights)
    w = np.array([weights[c] for c in cols], dtype=float)
    R = daily_ret[cols].values
    dates = daily_ret.index
    keys = {'D': dates.strftime('%Y%m%d'),
            'M': dates.strftime('%Y%m'),
            'Q': pd.Series(dates.year.astype(str).values + 'Q'
                           + np.ceil(dates.month / 3).astype(int).astype(str).values),
            'A': dates.year.astype(str)}[rebal]
    cur, prev_key = w.copy(), None
    rp = np.empty(len(R))
    for t in range(len(R)):
        if t > 0 and keys[t] != prev_key:
            cur = w.copy()
        rp[t] = cur @ R[t]
        tot = 1.0 + rp[t]
        if tot <= 0:
            raise SystemExit(f'组合归零 @ {dates[t]}')
        cur = cur * (1 + R[t]) / tot
        prev_key = keys[t]
    return pd.Series(rp, index=dates)


def metrics(rp: pd.Series, name: str) -> dict:
    eq = (1 + rp).cumprod()
    roll30 = (eq / eq.rolling(30).max() - 1).min()
    mon = eq.resample('ME').last().pct_change().min()
    return {
        'name': name,
        'yearly': yearly_returns(rp),
        'full_pct': round((eq.iloc[-1] - 1) * 100, 1),
        'maxdd_pct': round((eq / eq.cummax() - 1).min() * 100, 1),
        'dd30_worst_pct': round(roll30 * 100, 1),
        'worst_month_pct': round(mon * 100, 1),
    }


def s_verdict(m: dict) -> str:
    y = m['yearly']
    checks = [('S1', y.get(2025, -9e9) >= 36 and y.get(2026, -9e9) >= 22),
              ('S2', y.get(2024, -9e9) >= 44),
              ('S3', m['full_pct'] >= 1500),
              ('S4', m['dd30_worst_pct'] >= -30)]
    return ' '.join(f'{k}:{"PASS" if v else "FAIL"}' for k, v in checks)


def mc_bootstrap(rp: pd.Series, paths=2000, horizon=365, block=30) -> dict:
    r = rp.values
    nbl = int(np.ceil(horizon / block))
    rng = np.random.default_rng(SEED)
    sims = np.empty((paths, nbl * block))
    for i in range(paths):
        starts = rng.integers(0, len(r) - block, size=nbl)
        sims[i] = np.concatenate([r[s:s + block] for s in starts])
    sims = sims[:, :horizon]
    eq = np.cumprod(1 + sims, axis=1)
    yearly = eq[:, -1] - 1
    dd30s = np.array([min(eq[i, t] / eq[i, max(0, t - 29):t + 1].max() - 1
                          for t in range(horizon)) for i in range(paths)])
    return {
        'mc_dd30_p95_pct': round(np.percentile(dd30s, 5) * 100, 1),
        'mc_P_year_lt22_pct': round((yearly < 0.22).mean() * 100, 1),
        'mc_P_year_lt0_pct': round((yearly < 0).mean() * 100, 1),
        'mc_year_p50_pct': round(np.median(yearly) * 100, 1),
        'mc_year_p05_pct': round(np.percentile(yearly, 5) * 100, 1),
    }


# ── 袖曲线 ─────────────────────────────────────────────
lv2 = pd.read_csv(ROOT / 'research_lowvol/lv2/sleeves_daily.csv', index_col=0, parse_dates=True)
# 先归一索引(去 tz、归日),再提取列——顺序反了旧索引会被列 Series 持有
lv2.index = pd.DatetimeIndex(pd.to_datetime(lv2.index)).tz_localize(None).normalize()
B, A_vt, B_vt = lv2['B'], lv2['A_vt'], lv2['B_vt']
r3 = sleeve_daily_from_zip('backtest-result-2026-11-07_09-30-08.zip', 10000.0, 'SlowA_r3')
r2 = sleeve_daily_from_zip('backtest-result-2026-11-07_09-29-29.zip', 10000.0, 'SlowA_r2')

# 逐年校验(vs LV1 §2.1 表)
for s, known in [(r3, {2021: 83.8, 2022: 24.4, 2023: 131.1, 2024: 17.4, 2025: 114.9, 2026: 57.7}),
                 (r2, {2021: 53.9, 2022: 17.1, 2023: 92.3, 2024: 13.7, 2025: 70.6, 2026: 42.0})]:
    yv = yearly_returns(s.pct_change().fillna(0))
    dev = max(abs(yv[y] - known[y]) for y in known)
    print(f"校验 {s.name}: {yv} 最大年度偏差 {dev:.1f}pp"
          f"(LV1=钱包 mark-to-market 口径,本脚本=close-date 归因,容差 5pp)")
    assert dev < 5.0

# 统一日历:SlowA 2021-01-01→02-23 前导缺口按"资金闲置=初始值"补齐(首笔平仓前
# 无已实现盈亏,口径已披露)
full_idx = lv2.index


def extend_to_full(s: pd.Series, init: float) -> pd.Series:
    ext = s.reindex(full_idx)
    n_na = ext.isna().sum()
    assert ext.loc[ext.first_valid_index():].isna().sum() == 0, f'{s.name} 存在内部缺口'
    ext = ext.fillna(init)
    print(f'{s.name}: 前导补齐 {n_na} 天(资金闲置口径)')
    return ext


ret = pd.DataFrame({'B': B, 'SlowA_r3': extend_to_full(r3, 10000.0),
                    'SlowA_r2': extend_to_full(r2, 10000.0),
                    'A_vt': A_vt, 'B_vt': B_vt}).pct_change().fillna(0)

CONFIGS = {
    'cell40_r3(B30/Sr3x70)': ({'B': .30, 'SlowA_r3': .70},),
    'cell40_r2(B30/Sr2x70)': ({'B': .30, 'SlowA_r2': .70},),
    'cell49(Avt30/Bvt30/Sr3x40)': ({'A_vt': .30, 'B_vt': .30, 'SlowA_r3': .40},),
    'w25_75(B25/Sr3x75)': ({'B': .25, 'SlowA_r3': .75},),
    'w35_65(B35/Sr3x65)': ({'B': .35, 'SlowA_r3': .65},),
}
rows = []
champion = None
for name, (w,) in CONFIGS.items():
    for reb in ['D', 'M', 'Q', 'A']:
        rp = blend(ret[list(w)], w, reb)
        m = metrics(rp, f'{name}@{ {"D":"日","M":"月","Q":"季","A":"年"}[reb] }')
        m['rebal'] = {'D': '日', 'M': '月', 'Q': '季', 'A': '年'}[reb]
        m['S1-S4'] = s_verdict(m)
        if reb == 'M' and ('r3(B30' in name or 'Avt30' in name):
            m.update(mc_bootstrap(rp))
            tag = 'cell40r3' if 'r3(B30' in name else 'cell49'
            rp.to_frame('rp').to_csv(OUT / f'curve_{tag}_monthly.csv', index_label='date')
            if 'r3(B30' in name:
                champion = rp
        rows.append(m)

if champion is not None:
    champion.to_frame('rp').to_csv(OUT / 'champion_cell40r3_monthly_daily_returns.csv', index_label='date')

flat = []
for m in rows:
    row = {**{k: v for k, v in m.items() if k != 'yearly'}, **{f'y{y}': v for y, v in m['yearly'].items()}}
    flat.append(row)
res = pd.DataFrame(flat)
cols = ['name', 'rebal', 'y2021', 'y2022', 'y2023', 'y2024', 'y2025', 'y2026',
        'full_pct', 'maxdd_pct', 'dd30_worst_pct', 'worst_month_pct', 'S1-S4',
        'mc_dd30_p95_pct', 'mc_P_year_lt22_pct', 'mc_P_year_lt0_pct', 'mc_year_p50_pct', 'mc_year_p05_pct']
res[[c for c in cols if c in res.columns]].to_csv(OUT / 'assembly_results.csv', index=False)
print(res[[c for c in cols if c in res.columns]].to_string(index=False))
