# -*- coding: utf-8 -*-
"""LV2 build_sleeves.py — 从既有回测产物重建 5 条袖的日频权益/收益曲线并交叉校验。

数据源(全部只读,不写回源目录):
  A      = user_data/backtest_results/backtest-result-2026-11-07_03-54-11.zip (ARL_2x, init 7000)
  B      = user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip (OPT2_MomRegime15mLb21, init 3000)
  A_vt   = user_data/backtest_results/backtest-result-2026-11-07_06-45-22.zip (LVG_A_vt60f1, init 7000)
  B_vt   = user_data/backtest_results/lvg_full_b_2xvt.zip (LVG_B_2xvt, init 3000)
  SlowA  = research_revive/slowa/slowa_S12h_freqtrade_wallet.csv (init 10000, 日频 total_quote)

口径(对齐 research_improve/lvg/eval_lib.py):
  日曲线 = 小时 wallet total_quote resample('D').last();尾部锚定到 starting_balance+profit_total_abs
  yearly = 日曲线 groupby(year).last()/first()-1 (MTM 口径);另报 realized 口径(年内日 PnL 累计/年初权益)
  dd30   = e/e.rolling(30).max()-1,全窗最小值
输出: research_lowvol/lv2/sleeves_daily.csv, sleeve_check.csv
"""
import io
import json
import zipfile

import numpy as np
import pandas as pd

LAB = "/Users/caihaohan/Code/freqtrade-futures-lab"
OUT = f"{LAB}/research_lowvol/lv2"

ZIPS = {
    "A": f"{LAB}/user_data/backtest_results/backtest-result-2026-11-07_03-54-11.zip",
    "B": f"{LAB}/user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip",
    "A_vt": f"{LAB}/user_data/backtest_results/backtest-result-2026-11-07_06-45-22.zip",
    "B_vt": f"{LAB}/user_data/backtest_results/lvg_full_b_2xvt.zip",
}

# 已知参考数(charter / research_improve results.json / MASTER_REPORT),用于交叉校验
KNOWN_YEARLY = {
    "A": {2021: 171, 2022: 115, 2023: 123, 2024: 38, 2025: 26, 2026: 6},
    "B": {2021: 614, 2022: 2, 2023: 44, 2024: 140, 2025: 15, 2026: 8},
    "B_vt": {2021: 1352.9, 2022: 3.3, 2023: 88.3, 2024: 433.5, 2025: 23.4, 2026: 17.5},
    "SlowA": {2021: 25.8, 2022: 8.9, 2023: 46.1, 2024: 7.8, 2025: 32.9, 2026: 18.3},
}
KNOWN_TOTAL = {"A_vt": 4672.1, "B_vt": 21760.8}


def load_zip_wallet(zpath):
    zf = zipfile.ZipFile(zpath)
    jname = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n][0]
    j = json.loads(zf.read(jname))
    sname = list(j["strategy"].keys())[0]
    st = j["strategy"][sname]
    wname = [n for n in zf.namelist() if n.endswith("_wallet.feather")][0]
    w = pd.read_feather(io.BytesIO(zf.read(wname))).set_index("date").sort_index()
    hourly = w["total_quote"].resample("h").last().ffill()
    anchor = st["starting_balance"] + st["profit_total_abs"]
    liqs = sum(1 for t in st["trades"] if t.get("is_liquidation"))
    return sname, hourly, st["starting_balance"], anchor, liqs


def anchor_tail(curve, anchor):
    """尾部锚定(对齐 eval_lib.anchor_tail):最后一个自然日内插到 anchor。"""
    c = curve.copy()
    tail = c.index >= c.index[-1].floor("D")
    base = c[~tail].iloc[-1] if (~tail).any() else c.iloc[0]
    n = max(int(tail.sum()), 2)
    c[tail] = np.linspace(base, anchor, n)[-int(tail.sum()):]
    c.iloc[-1] = anchor
    return c


def daily_series(hourly, anchor):
    d = anchor_tail(hourly, anchor).resample("D").last()
    return d


sleeves = {}
meta = {}
for tag, zp in ZIPS.items():
    sname, hourly, start, anchor, liqs = load_zip_wallet(zp)
    d = daily_series(hourly, anchor)
    sleeves[tag] = d
    meta[tag] = dict(strategy=sname, init=start, final=anchor, liq=liqs)

# SlowA: 日频 csv
sw = pd.read_csv(f"{LAB}/research_revive/slowa/slowa_S12h_freqtrade_wallet.csv", parse_dates=["date"])
slow = sw.set_index("date")["total_quote"].resample("D").last().ffill()
sleeves["SlowA"] = slow
meta["SlowA"] = dict(strategy="slowa_S12h (wallet csv)", init=10000.0, final=float(slow.iloc[-1]), liq=0)

# ---- 指标函数(eval_lib 口径)----
def yearly_mtm(d):
    g = d.groupby(d.index.year)
    return (g.last() / g.first() - 1) * 100


def yearly_realized(d):
    pnl = d.diff().fillna(d.iloc[0] - meta.get(d.name, {}).get("init", d.iloc[0]))
    out = {}
    base_eq = None
    for y in d.index.year.unique():
        yr_pnl = pnl[pnl.index.year == y].sum()
        start_eq = d[d.index.year == y].iloc[0]
        out[y] = yr_pnl / start_eq * 100
    return pd.Series(out)


def dd30_all(d):
    return (d / d.rolling(30).max() - 1).min() * 100


def maxdd(d):
    return (d / d.cummax() - 1).min() * 100


# ---- 输出日频曲线(对齐到公共日历)----
idx = None
for t, s in sleeves.items():
    idx = s.index if idx is None else idx.union(s.index)
daily = pd.DataFrame({t: s.reindex(idx).ffill() for t, s in sleeves.items()})
daily.index.name = "date"
daily.to_csv(f"{OUT}/sleeves_daily.csv")

rets = daily / daily.shift(1) - 1
rets.iloc[0] = 0.0

# ---- 交叉校验表 ----
rows = []
for t in ["A", "B", "A_vt", "B_vt", "SlowA"]:
    d = daily[t].dropna()
    ym = yearly_mtm(d)
    yr = yearly_realized(d)
    row = dict(
        sleeve=t,
        strategy=meta[t]["strategy"],
        init=meta[t]["init"],
        final=round(meta[t]["final"], 1),
        total_pct=round((meta[t]["final"] / meta[t]["init"] - 1) * 100, 1),
        liquidations=meta[t]["liq"],
        maxdd_pct=round(maxdd(d), 1),
        dd30_worst=round(dd30_all(d), 1),
    )
    for y in range(2021, 2027):
        row[f"y{y}_mtm"] = round(ym.get(y, np.nan), 1)
        row[f"y{y}_realized"] = round(yr.get(y, np.nan), 1)
        row[f"y{y}_known"] = KNOWN_YEARLY.get(t, {}).get(y, np.nan)
        k = row[f"y{y}_known"]
        if not np.isnan(k):
            row[f"y{y}_dev_mtm"] = round(row[f"y{y}_mtm"] - k, 1)
            row[f"y{y}_dev_realized"] = round(row[f"y{y}_realized"] - k, 1)
    rows.append(row)

chk = pd.DataFrame(rows)
chk.to_csv(f"{OUT}/sleeve_check.csv", index=False)

# ---- 复合校验:AB70/30 与 ★(buy-and-hold 加权合成,对齐 eval_lib.portfolio)----
def synth_bah(a, b, wa, wb):
    idx = a.index.union(b.index)
    x = a.reindex(idx).ffill() / a.iloc[0] * wa
    y = b.reindex(idx).ffill() / b.iloc[0] * wb
    return (x.fillna(wa) + y.fillna(wb))


ab = synth_bah(daily["A"], daily["B"], 7000, 3000)
star = synth_bah(daily["A_vt"], daily["B_vt"], 7000, 3000)
synth_rows = []
for nm, p, known in [
    ("AB7030_bah", ab, {2021: 303.6, 2022: 54.9, 2023: 95.2, 2024: 64.1, 2025: 21.5, 2026: 3.7}),
    ("STAR_vt_bah", star, {2023: 176.7, 2024: 137.5, 2025: 37.4, 2026: 7.6}),
]:
    ym = yearly_mtm(p)
    r = dict(combo=nm, final=round(float(p.iloc[-1]), 0),
             total_pct=round((p.iloc[-1] / 10000 - 1) * 100, 1),
             dd30_worst=round(dd30_all(p), 1), maxdd_pct=round(maxdd(p), 1))
    for y in range(2021, 2027):
        r[f"y{y}"] = round(ym.get(y, np.nan), 1)
        r[f"y{y}_known"] = known.get(y, np.nan)
    synth_rows.append(r)
pd.DataFrame(synth_rows).to_csv(f"{OUT}/combo_check.csv", index=False)

print("== sleeve_check ==")
print(chk[["sleeve", "total_pct", "maxdd_pct", "dd30_worst"] + [c for c in chk.columns if c.startswith("y20") and c.endswith("_mtm")]].to_string(index=False))
print("== combo_check ==")
print(pd.DataFrame(synth_rows).to_string(index=False))
print("\nsaved: sleeves_daily.csv / sleeve_check.csv / combo_check.csv")
