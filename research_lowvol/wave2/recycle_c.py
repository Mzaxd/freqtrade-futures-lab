# -*- coding: utf-8 -*-
"""research_lowvol wave2 addendum — "C 回收 B 闲置资金"近似测试(户主提议,2026-11-08)

问题:B 的 regime 门(BTC日线>SMA100×1.03)关闭时 B 资金闲置;当前冠军 A_vt 袖内含
RECYCLE_MULT=1.21(已把这笔闲钱借给 A)。测试:改借给 C(SlowA)是否更优。

变体(装配层近似,日收益缩放;stake 级回收的线性近似,已披露):
- V0 基线 cell49:A_vt30/B_vt30/C_r3 40(A 内含 recycle 1.21)
- V1 换借款人:门关日 A_vt÷1.21(剥除其回收)、C_r3×1.28
- V2 分半借:门关日 A_vt÷1.105、C_r3×1.14
- V3 C 降基准+多借:门关日 A_vt÷1.21、C_r2×1.50(有效 ~3%risk,避开 r3 截断区)
口径同 wave2(月度再平衡、真实曲线、close-date 归因);门状态滞后 1 天(因果)。
"""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('/Users/caihaohan/Code/freqtrade-futures-lab')
BT = ROOT / 'user_data/backtest_results'
OUT = ROOT / 'research_lowvol/wave2'
SEED = 20261107


def sleeve_daily_from_zip(zname, init, col):
    with zipfile.ZipFile(BT / zname) as z:
        j = [n for n in z.namelist() if n.endswith('.json') and 'config' not in n][0]
        st = json.loads(z.read(j))['strategy']
        strat = st[list(st.keys())[0]]
        df = pd.DataFrame([{'d': t['close_date'][:10], 'p': t['profit_abs']}
                           for t in strat['trades']])
        day = df.groupby('d')['p'].sum().sort_index()
        idx = pd.date_range(day.index.min(), day.index.max(), freq='D')
        eq = init + day.reindex(idx.strftime('%Y-%m-%d')).fillna(0).cumsum().values
        eq[-1] = float(strat['final_balance'])
        return pd.Series(eq, index=idx, name=col)


def yearly_returns(rp):
    eq = (1 + rp).cumprod()
    ye = eq.resample('YE').last()
    prev = np.r_[1.0, ye.values[:-1]]
    return {int(i.year): round((v / p - 1) * 100, 1) for i, v, p in zip(ye.index, ye.values, prev)}


def blend(daily_ret, weights, rebal='M'):
    cols = list(weights)
    w = np.array([weights[c] for c in cols], float)
    R = daily_ret[cols].values
    dates = daily_ret.index
    keys = {'M': dates.strftime('%Y%m'), 'D': dates.strftime('%Y%m%d')}[rebal]
    cur, prev_key = w.copy(), None
    rp = np.empty(len(R))
    for t in range(len(R)):
        if t > 0 and keys[t] != prev_key:
            cur = w.copy()
        rp[t] = cur @ R[t]
        tot = 1.0 + rp[t]
        cur = cur * (1 + R[t]) / tot
        prev_key = keys[t]
    return pd.Series(rp, index=dates)


def metrics(rp, name):
    eq = (1 + rp).cumprod()
    return {'name': name,
            'yearly': yearly_returns(rp),
            'full_pct': round((eq.iloc[-1] - 1) * 100, 1),
            'maxdd_pct': round((eq / eq.cummax() - 1).min() * 100, 1),
            'dd30_worst_pct': round((eq / eq.rolling(30).max() - 1).min() * 100, 1)}


def mc(rp, paths=2000, horizon=365, block=30):
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
    return {'mc_dd30_p95': round(np.percentile(dd30s, 5) * 100, 1),
            'mc_P_y_lt0': round((yearly < 0).mean() * 100, 1),
            'mc_y_p50': round(np.median(yearly) * 100, 1)}


# ── regime 门(B 的门:BTC 日线收盘 > SMA100×1.03,滞后1天) ──
btc = pd.read_feather(ROOT / 'user_data/data/binance/futures/BTC_USDT_USDT-1d-futures.feather')
btc['date'] = pd.to_datetime(btc['date']).dt.tz_localize(None).dt.normalize()
btc = btc.set_index('date')['close'].sort_index()
# 注意:bool 列 shift(1) 会变 object(装不下 NaN),`~object` 是按位非(~True=-2)——必须 astype(bool)
gate_on = (btc > btc.rolling(100).mean() * 1.03)  # SMA 未热身的 NaN 比较自动为 False

# ── 袖曲线 ──
lv2 = pd.read_csv(ROOT / 'research_lowvol/lv2/sleeves_daily.csv', index_col=0, parse_dates=True)
lv2.index = pd.DatetimeIndex(pd.to_datetime(lv2.index)).tz_localize(None).normalize()
A_vt, B_vt, B = lv2['A_vt'], lv2['B_vt'], lv2['B']
r3 = sleeve_daily_from_zip('backtest-result-2026-11-07_09-30-08.zip', 10000.0, 'C_r3')
r2 = sleeve_daily_from_zip('backtest-result-2026-11-07_09-29-29.zip', 10000.0, 'C_r2')

full = lv2.index
r3e = r3.reindex(full).fillna(10000.0)
r2e = r2.reindex(full).fillna(10000.0)
gate = gate_on.shift(1).reindex(full).fillna(False).astype(bool)  # 因果:今日状态由昨收定
off = ~gate  # 门关 = B 闲置(纯 bool,~ 为逻辑非)
assert off.dtype == bool and off.isin([True, False]).all()
print('门关(B 闲置)天数占比 by year:',
      {int(y): round(v * 100) for y, v in off.groupby(off.index.year).mean().items()})

ret = pd.DataFrame({'A_vt': A_vt, 'B_vt': B_vt, 'C_r3': r3e, 'C_r2': r2e}).pct_change().fillna(0)

# ── 变体 ──
W = {'A_vt': .30, 'B_vt': .30}


def make_variant(tag, a_div, c_col, c_mult):
    r = ret.copy()
    r['A_vt'] = np.where(off, r['A_vt'] / a_div, r['A_vt'])
    r[c_col] = np.where(off, r[c_col] * c_mult, r[c_col])
    w = {**W, c_col: .40}
    rp = blend(r[list(w)], w)
    m = metrics(rp, tag)
    y = m['yearly']
    m['S1-S4'] = ' '.join([
        f"S1:{'P' if y.get(2025, -9e9) >= 36 and y.get(2026, -9e9) >= 22 else 'F'}",
        f"S2:{'P' if y.get(2024, -9e9) >= 44 else 'F'}",
        f"S3:{'P' if m['full_pct'] >= 1500 else 'F'}",
        f"S4:{'P' if m['dd30_worst_pct'] >= -30 else 'F'}"])
    return m, rp


rows, curves = [], {}
for tag, a_div, c_col, cm in [
    ('V0 基线(钱借A×1.21)', 1.0, 'C_r3', 1.0),
    ('V1 换借款人(借C×1.28)', 1.21, 'C_r3', 1.28),
    ('V2 分半借(A1.105/C1.14)', 1.105, 'C_r3', 1.14),
    ('V3 C_r2×1.50+A不借', 1.21, 'C_r2', 1.50),
]:
    m, rp = make_variant(tag, a_div, c_col, cm)
    m.update(mc(rp))
    rows.append(m)
    curves[tag] = rp

res = pd.DataFrame([{**{k: v for k, v in m.items() if k != 'yearly'},
                     **{f'y{y}': v for y, v in m['yearly'].items()}} for m in rows])
res.to_csv(OUT / 'recycle_c_results.csv', index=False)
print(res[['name', 'y2021', 'y2022', 'y2023', 'y2024', 'y2025', 'y2026', 'full_pct',
           'maxdd_pct', 'dd30_worst_pct', 'S1-S4',
           'mc_dd30_p95', 'mc_P_y_lt0', 'mc_y_p50']].to_string(index=False))
for tag, rp in curves.items():
    rp.to_frame('rp').to_csv(OUT / f"recycle_curve_{tag[:2]}.csv", index_label='date')
