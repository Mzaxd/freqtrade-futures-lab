# -*- coding: utf-8 -*-
"""LV4 彩票袖裁决(research_lowvol/lv4)— 只读既有 zip/csv,0 次新回测。

任务:新币"彩票袖"(uni_oos_b 新币腿)作为小权重附加,在 dd30 ≥ -30% 放宽线下值多少、
尾部多深。装配级近似:月度再平衡,组合日曲线算 dd30。

口径(重要,报告 §2 详述):
- 彩票腿日收益 = 新币腿当日平仓 PnL / 臂b钱包前一日末权益。
  理由:臂 b 内仓位按臂权益定 risk_pct;袖式装配下仓位按袖权益等比缩放,收益率不变;
  避免"独立 7000 袖 2024 被打穿"的保证金幻觉(伪权益 2024 年 -86%)。
- 基座 = A(03-54-11, init 7000) 35% + B(03-56-10, init 3000) 15% + SlowA_12h×2(init 10000) 50%,
  月度再平衡。SlowA2x = S12h 日收益 ×2(线性杠杆近似)。
- 组合 = (1-w)·基座 + w·彩票,月度再平衡,w ∈ {10,15,25}%。
- 幸存者下界:退市准入月(TON/MBL/FRONT,预注册候选集=2022+上市)彩票腿月收益
  (a) 保守=历史最差月;(b) 悲观=-20%。月内日形状按月收益线性缩放保留。
"""
import io
import json
import math
import zipfile

import numpy as np
import pandas as pd

LAB = "/Users/caihaohan/Code/freqtrade-futures-lab"
OUT = f"{LAB}/research_lowvol/lv4"
FROZEN12 = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
            "LINK", "DOT", "LTC", "UNI"}
AGE_MIN, LIQ_MIN, RV_MIN = 60, 10_000_000.0, 0.60  # build_universe.py 冻结常数
IDX = pd.date_range("2021-01-01", "2026-11-07", freq="D", tz="UTC")
PER = IDX.to_period("M")


# ---------------------------------------------------------------- 加载
def load_zip(zip_path, strat_hint=""):
    """返回 (日度权益 Series, 逐笔 DataFrame, 策略统计 dict)。"""
    with zipfile.ZipFile(zip_path) as z:
        jname = [n for n in z.namelist() if n.endswith(".json")
                 and "config" not in n
                 and n.split("/")[-1].startswith("backtest-result")][0]
        d = json.load(z.open(jname))
        skey = ([k for k in d["strategy"] if strat_hint in k][0]
                if strat_hint else list(d["strategy"])[0])
        s = d["strategy"][skey]
        tr = pd.DataFrame(s["trades"])
        wname = [n for n in z.namelist() if n.endswith("_wallet.feather")][0]
        wf = pd.read_feather(io.BytesIO(z.read(wname)))
    eq = (wf[["date", "total_quote"]].drop_duplicates("date", keep="last")
          .set_index("date")["total_quote"].sort_index())
    eq_d = eq.resample("1D").last().ffill()
    # 终值锚定 profit_total_abs(lab 惯例;钱包 feather 末值系统性低于 final_balance,
    # 差额集中在窗口末尾,只影响 2026 年末值;校验:A 锚定后 2026=+6.0 与 CONTEXT 一致)
    fb = s.get("final_balance")
    if fb and fb > 0:
        eq_d.iloc[-1] = fb
    for c in ("open_date", "close_date"):
        tr[c] = pd.to_datetime(tr[c], utc=True)
    tr["base"] = tr["pair"].str.split("/").str[0]
    return eq_d, tr, s


def yearly_from_daily(eq: pd.Series) -> dict:
    e = eq.groupby(eq.index.year).last()
    prev = e.shift(1)
    prev.iloc[0] = eq.iloc[0]
    return {int(k): round(v * 100, 1) for k, v in (e / prev - 1).items()}


def dd30_min(eq: pd.Series) -> pd.Series:
    return (eq / eq.rolling("30D", min_periods=2).max() - 1) * 100


def month_end_rescale(r_daily: pd.Series, m_target: pd.Series) -> pd.Series:
    """把日收益序列逐月线性缩放(月内累计超额增长 ×k),使月收益精确命中目标;
    月形状保留。目标月实际收益为 0 时按日均摊(披露)。"""
    out = r_daily.copy()
    for m, tgt in m_target.items():
        mask = PER == m
        if not mask.any():
            continue
        g = (1 + r_daily[mask]).cumprod()  # 月内累计增长
        actual = g.iloc[-1] - 1
        if abs(tgt - actual) < 1e-12:
            continue
        if abs(actual) < 1e-12:
            r = np.full(mask.sum(), (1 + tgt) ** (1 / mask.sum()) - 1)
        else:
            k = tgt / actual
            g2 = 1 + k * (g - 1)
            r = g2 / g2.shift(1).fillna(1) - 1
        out[mask] = r.values
    return out


def portfolio(daily_rets: dict, weights: dict) -> pd.Series:
    """月度再平衡组合的日权益(初始 1)。月初按目标权重分资本,月内各自复利,月末再平衡。"""
    growths = {k: (1 + v).cumprod() for k, v in daily_rets.items()}
    vals = np.empty(len(IDX))
    capital = 1.0
    prev_g = {k: 1.0 for k in growths}
    i0 = 0
    for m in PER.unique():
        mask = np.asarray(PER == m)
        n = mask.sum()
        month_val = np.zeros(n)
        for k, g in growths.items():
            gm = g.values[mask]
            rel = gm / (prev_g[k] if i0 > 0 or True else 1.0)
            month_val += weights[k] * rel
        # prev_g 更新为该月末累计增长
        for k, g in growths.items():
            prev_g[k] = g.values[mask][-1]
        vals[i0:i0 + n] = capital * month_val
        capital = capital * month_val[-1]
        i0 += n
    return pd.Series(vals, index=IDX)


# ---------------------------------------------------------------- 1) 三条基座曲线
eqA, trA, sA = load_zip(f"{LAB}/user_data/backtest_results/backtest-result-2026-11-07_03-54-11.zip")
eqB, trB, sB = load_zip(f"{LAB}/user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip")
sw = pd.read_csv(f"{LAB}/research_revive/slowa/slowa_S12h_freqtrade_wallet.csv")
sw["date"] = pd.to_datetime(sw["date"], utc=True)
eqS = sw.set_index("date")["total_quote"].sort_index().resample("1D").last().ffill()

rA = eqA.reindex(IDX).ffill().pct_change()
rB = eqB.reindex(IDX).ffill().pct_change()
rS = 2 * eqS.reindex(IDX).ffill().pct_change()  # SlowA_12h ×2 线性杠杆近似
for r in (rA, rB, rS):
    r.iloc[0] = 0.0
    r.fillna(0.0, inplace=True)

print("=== 校验:基座逐年收益 %(日度钱包首尾) vs CONTEXT 已知 ===")
print("A  袖:", yearly_from_daily(eqA), "| 已知 171/115/123/38/26/6")
print("B  袖:", yearly_from_daily(eqB), "| 已知 614/2/44/140/15/8")
print("SlowA:", yearly_from_daily(eqS), "| 已知 25.8/8.9/46.1/7.8/32.9/18.3")
liqA = int(trA["exit_reason"].str.contains("liquidation", case=False).sum())
liqB = int(trB["exit_reason"].str.contains("liquidation", case=False).sum())
print(f"强平:A 袖 {liqA} 笔 / B 袖 {liqB} 笔")

# ---------------------------------------------------------------- 2) 彩票腿(uni_oos_b 新币腿)
eqUB, trUB, sUB = load_zip(f"{LAB}/user_data/backtest_results/uni_oos_b.zip", "uni_ARL_ext")
print("\n=== 校验:臂 b(uni_ARL_ext)逐年 ===")
print("臂b:", yearly_from_daily(eqUB), "| 已知 23-26: 128.6/-4.0/133.8/80.8")
liqUB = int(trUB["exit_reason"].str.contains("liquidation", case=False).sum())
print(f"臂b 强平 {liqUB} 笔 | is_open {int(trUB['is_open'].sum())} 笔")
print("臂b 诊断: profit_total_abs =", round(sUB.get("profit_total_abs", float("nan"))),
      "final_balance =", round(sUB.get("final_balance", float("nan"))),
      "wallet 末值 =", round(eqUB.iloc[-1], 1), "钱包末日 =", eqUB.index[-1].date())
if liqUB:
    lk = trUB[trUB["exit_reason"].str.contains("liquidation", case=False)]
    print("强平逐笔:", lk[["pair", "open_date", "close_date", "profit_abs",
                          "is_short"]].to_dict("records"))

newleg = trUB[~trUB["base"].isin(FROZEN12)].copy()
newleg["month"] = newleg["close_date"].dt.to_period("M")
print("\n新币腿逐年净额(USDT,平仓月):",
      {int(y): round(v) for y, v in
       newleg.groupby(newleg["close_date"].dt.year)["profit_abs"].sum().items()})
print("uni2 已知: 2023 -157 / 2024 -5942 / 2025 +22198 / 2026 +22151")

eqUB_d = eqUB.reindex(IDX).ffill()


def leg_daily(leg: pd.DataFrame) -> pd.Series:
    dp = leg.groupby(leg["close_date"].dt.normalize())["profit_abs"].sum()
    dp = dp.reindex(IDX).fillna(0.0)
    r = dp / eqUB_d.shift(1).fillna(7000.0)
    r.iloc[0] = 0.0
    return r.fillna(0.0).clip(-0.95, 5.0)


rL = leg_daily(newleg)
mL = (1 + rL).groupby(PER).prod() - 1
print("\n彩票腿逐年收益 %(对臂b权益归一):",
      {int(y): f"{v*100:+.1f}" for y, v in
       ((1 + mL).groupby(mL.index.year).prod() - 1).items()})
print("彩票腿最差5月:", {str(k): f"{v*100:+.1f}%" for k, v in mL.nsmallest(5).items()})
print("彩票腿最好3月:", {str(k): f"{v*100:+.1f}%" for k, v in mL.nlargest(3).items()})
print(f"彩票腿月命中率: {int((mL>0).sum())}/{len(mL)} 为正")
for coin in ("ENA", "MYX"):
    sub = newleg[newleg["base"] == coin]
    mm = {str(k): round(v) for k, v in sub.groupby("month")["profit_abs"].sum().items()
          if abs(v) > 100}
    print(f"{coin}: n={len(sub)} net={sub['profit_abs'].sum():+.0f} 大月={mm}")

# ---------------------------------------------------------------- 3) 退市准入月(严格重算)
def admit(sym_csv: str, months) -> list:
    df = pd.read_csv(sym_csv)
    idxd = pd.to_datetime(df["date"].astype("int64"), unit="ms", utc=True)
    s = pd.DataFrame({"qv": df["quote_volume"].astype(float).values,
                      "close": df["close"].astype(float).values},
                     index=idxd).sort_index()
    out = []
    for m in months:
        m0 = m.to_timestamp(how="start").tz_localize("UTC")
        h = s[s.index < m0]
        if len(h) < 30:
            continue
        age = (m0 - h.index[0]).days
        l30 = h.iloc[-30:]
        liq = float(l30["qv"].median())
        r = np.log(l30["close"] / l30["close"].shift(1)).dropna()
        rv = float(r.std() * math.sqrt(365)) if len(r) >= 15 else float("nan")
        stale = (m0 - h.index[-1]).days > 3  # 数据中断/退市视同不达标(预注册 §1)
        if age >= AGE_MIN and liq >= LIQ_MIN and rv == rv and rv >= RV_MIN and not stale:
            out.append(str(m))
    return out


months = pd.period_range("2023-01", "2026-11", freq="M")
DELIST_CORE = ["TONUSDT", "MBLUSDT", "FRONTUSDT"]   # 2022+ 上市 = 臂b候选设计集内
DELIST_WIDE = ["FTMUSDT", "WAVESUSDT", "TOMOUSDT"]  # 2021 前上市 = 臂b设计集外(披露)
core_m = {s: admit(f"{LAB}/research_improve/uni/daily/{s}.csv", months) for s in DELIST_CORE}
wide_m = {s: admit(f"{LAB}/research_improve/uni/daily/{s}.csv", months) for s in DELIST_WIDE}
aff_core = sorted({m for v in core_m.values() for m in v})
aff_wide_extra = sorted({m for v in wide_m.values() for m in v} - set(aff_core))
print("\n=== 退市准入月(按冻结规则严格重算;陈旧数据=不达标)===")
for k, v in core_m.items():
    print(f"  核心 {k}: {len(v)} 月 {v}")
for k, v in wide_m.items():
    print(f"  宽口径 {k}(设计集外): {len(v)} 月")
print(f"  核心并集 {len(aff_core)} 月:{aff_core}")
print(f"  宽口径另增 {len(aff_wide_extra)} 月:{aff_wide_extra}")

# ---------------------------------------------------------------- 4) 装配与网格
W_BASE = {"A": 0.35, "B": 0.15, "S2": 0.50}


def build_combo(m_lot: pd.Series, w: float):
    rl = month_end_rescale(rL, m_lot) if not m_lot.equals(mL) else rL
    eq = portfolio({"A": rA, "B": rB, "S2": rS, "L": rl},
                   {"A": W_BASE["A"] * (1 - w), "B": W_BASE["B"] * (1 - w),
                    "S2": W_BASE["S2"] * (1 - w), "L": w})
    mret = (1 + rl).groupby(PER).prod() - 1  # 仅用于最差单月展示(彩票腿)
    return eq, mret


def report(eq: pd.Series, name: str) -> dict:
    yr = yearly_from_daily(eq)
    dd = dd30_min(eq)
    dd_y = {int(k): round(v, 1) for k, v in dd.groupby(dd.index.year).min().items()}
    mcomb = eq.groupby(PER).last() / eq.groupby(PER).first().shift(1) - 1
    return {"name": name, "y": yr, "dd30_y": dd_y,
            "dd30_worst": round(dd.min(), 1),
            "worst_m": round(mcomb.min() * 100, 1),
            "total": round((eq.iloc[-1] / 1 - 1) * 100, 0)}


eq_base, _ = build_combo(mL * 0, 0.0)
base_rep = report(eq_base, "基座(A35/B15/SlowA2x50,w=0)")
print("\n=== 基座 ===")
print(base_rep)

mL_cons, mL_pess = mL.copy(), mL.copy()
mL_cons[mL_cons.index.astype(str).isin(aff_core)] = mL.min()
mL_pess[mL_pess.index.astype(str).isin(aff_core)] = -0.20

grid = []
for cal, mser in [("as-is", mL), ("保守", mL_cons), ("悲观", mL_pess)]:
    for w in (0.10, 0.15, 0.25):
        eq, _ = build_combo(mser, w)
        rep = report(eq, f"{cal} w={int(w*100)}%")
        y, by = rep["y"], base_rep["y"]
        rep.update({"cal": cal, "w": w,
                    "d25": round(y[2025] - by[2025], 1),
                    "d26": round(y[2026] - by[2026], 1),
                    "drag24": round(by[2024] - y[2024], 1),
                    "S1": y[2025] >= 36 and y[2026] >= 22,
                    "S2": y[2024] >= 44,
                    "S3": rep["total"] >= 1500,
                    "S4": rep["dd30_worst"] >= -30})
        grid.append(rep)

print("\n=== 9 格网格 ===")
for g in grid:
    print(g)

print("\n=== 彩票腿自身逐年(三口径;受影响月数 23:1 / 24:9 / 25:7 / 26:3)===")
for cal, mser in [("as-is", mL), ("保守", mL_cons), ("悲观", mL_pess)]:
    yr = (1 + mser).groupby(mser.index.year).prod() - 1
    print(f"  {cal}:", {int(k): f"{v*100:+.1f}%" for k, v in yr.items()})
print("  2025 月度:", {str(k): f"{v*100:+.1f}" for k, v in mL[mL.index.year == 2025].items()})
print("  2026 月度:", {str(k): f"{v*100:+.1f}" for k, v in mL[mL.index.year == 2026].items()})

print("\n=== 单袖 maxDD(S4 后半:≤50%)===")
for nm, eq_ in [("A", eqA), ("B", eqB), ("SlowA2x", (1 + rS).cumprod() * 10000)]:
    print(f"  {nm}: {(eq_/eq_.cummax()-1).min()*100:.1f}%")
eqL = (1 + rL).cumprod() * 7000
print(f"  彩票腿(as-is,平仓结算近似): {(eqL/eqL.cummax()-1).min()*100:.1f}%")

# ---------------------------------------------------------------- 5) 压力(w=15%, as-is)
print("\n=== 压力测试(w=15%, as-is)===")
stress = []
for tag, drop in [("剔ENA", {"ENA"}), ("剔MYX", {"MYX"}), ("双剔", {"ENA", "MYX"})]:
    ml_ = (1 + leg_daily(newleg[~newleg["base"].isin(drop)])).groupby(PER).prod() - 1
    eq, _ = build_combo(ml_, 0.15)
    rep = report(eq, f"压力 {tag}")
    y, by = rep["y"], base_rep["y"]
    rep.update({"d25": round(y[2025] - by[2025], 1), "d26": round(y[2026] - by[2026], 1),
                "drag24": round(by[2024] - y[2024], 1),
                "S1": y[2025] >= 36 and y[2026] >= 22, "S2": y[2024] >= 44,
                "S3": rep["total"] >= 1500, "S4": rep["dd30_worst"] >= -30})
    stress.append(rep)
    print(rep)

# ---------------------------------------------------------------- 6) 落盘
pd.DataFrame(grid).to_csv(f"{OUT}/grid_9cells.csv", index=False)
pd.DataFrame(stress).to_csv(f"{OUT}/stress_3cells.csv", index=False)
mL.rename("r_lottery").to_frame().to_csv(f"{OUT}/lottery_monthly.csv")
pd.DataFrame({"r_base_A": rA, "r_base_B": rB, "r_slow2x": rS, "r_lottery": rL}
             ).to_csv(f"{OUT}/daily_returns.csv")
eq_base.to_frame("eq_base").assign(eq_lottery=eqL).to_csv(f"{OUT}/curves.csv")
with open(f"{OUT}/delisted_months.json", "w") as f:
    json.dump({"core": core_m, "wide": wide_m, "aff_core": aff_core,
               "aff_wide_extra": aff_wide_extra}, f, indent=1)
print("\n已写盘 →", OUT)
