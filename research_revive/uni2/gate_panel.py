"""uni2 — 环境门候选变量月度面板 + 对新币腿逐月 PnL 的门控模拟(轻量 pandas,不跑回测)。

门控语义:门在月初 M 生效,变量只用 M 之前日线(严格因果);
门 OFF → 该月新开仓禁止(近似:删除 open_date 落在该月的新币腿交易)。
"""
import json
import math
import os
import zipfile

import numpy as np
import pandas as pd

LAB = "/Users/caihaohan/Code/freqtrade-futures-lab"
UNI = f"{LAB}/research_improve/uni"
FROZEN12 = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
            "LINK", "DOT", "LTC", "UNI"]


def load_trades(zip_path, sname=None):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist()
                 if n.endswith(".json") and "config" not in n
                 and n.split("/")[-1].startswith("backtest-result")]
        with z.open(names[0]) as f:
            d = json.load(f)
        skey = sname or list(d["strategy"].keys())[0]
        tr = pd.DataFrame(d["strategy"][skey]["trades"])
    tr["open_date"] = pd.to_datetime(tr["open_date"], utc=True)
    tr["base"] = tr["pair"].str.split("/").str[0]
    return tr


def load_daily() -> dict[str, pd.Series]:
    """close 序列:research_improve/uni/daily/*.csv(574 币,含退市)+ 冻结12 feather。"""
    out = {}
    for fn in os.listdir(f"{UNI}/daily"):
        if not fn.endswith(".csv"):
            continue
        df = pd.read_csv(f"{UNI}/daily/{fn}")
        if len(df) < 10:
            continue
        idx = pd.to_datetime(df["date"].astype("int64"), unit="ms", utc=True)
        out[fn[:-4]] = pd.Series(df["close"].astype(float).values, index=idx)
    for c in FROZEN12:
        fe = pd.read_feather(
            f"{LAB}/user_data/data/binance/futures/{c}_USDT_USDT-1d-futures.feather")
        idx = pd.DatetimeIndex(fe["date"])
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        out[c + "USDT"] = pd.Series(fe["close"].astype(float).values, index=idx)
    return {k: v.sort_index()[~v.sort_index().index.duplicated()]
            for k, v in out.items()}


def admit_series(s: pd.Series, m0) -> tuple[bool, dict]:
    h = s[s.index < m0]
    if len(h) < 30:
        return False, {}
    age = (m0 - h.index[0]).days
    l30 = h.iloc[-30:]
    qv = None
    r = np.log(l30 / l30.shift(1)).dropna()
    rv = float(r.std() * math.sqrt(365)) if len(r) >= 15 else float("nan")
    ok = age >= 60 and (rv == rv and rv >= 0.60)
    return ok, {"age": age, "rv30": rv}


def main():
    daily = load_daily()
    ext = pd.read_csv(f"{UNI}/universe_ext.csv")          # (pair, month) 可回测新币
    ext_pairs = ext["pair"].str.split("/").str[0] + "USDT"
    ext["sym"] = ext_pairs
    active_new = {m: set(g["sym"]) for m, g in ext.groupby("month")}

    tr_b = load_trades(f"{LAB}/user_data/backtest_results/uni_oos_b.zip")
    tr_b["om"] = tr_b["open_date"].dt.strftime("%Y-%m")
    newleg = tr_b[~tr_b["base"].isin(FROZEN12)]
    pnl_open_month = newleg.groupby("om").agg(
        pnl=("profit_abs", "sum"), n=("profit_abs", "size"))

    btc = daily["BTCUSDT"]
    months = pd.period_range("2023-01", "2026-11", freq="M")
    rows = []
    for month in months:
        m0 = month.to_timestamp(how="start").tz_localize("UTC")
        m1 = (month + 1).to_timestamp(how="start").tz_localize("UTC")
        mstr = str(month)
        syms = active_new.get(mstr, set())
        # --- 新币篮子变量(只用 m0 前数据)---
        rvs, ret30s, above50, ages = [], [], [], 0
        for sym in syms:
            s = daily.get(sym)
            if s is None:
                continue
            h = s[s.index < m0]
            if len(h) < 35:
                continue
            ok, d = admit_series(s, m0)
            if not ok:
                continue
            rvs.append(d["rv30"])
            l30 = h.iloc[-30:]
            ret30s.append(l30.iloc[-1] / l30.iloc[0] - 1)
            sma50 = h.iloc[-50:].mean()
            above50.append(1.0 if h.iloc[-1] > sma50 else 0.0)
            ages += d["age"]
        # --- 冻结12变量 ---
        fr_rvs, fr_ret30 = [], []
        for c in FROZEN12:
            s = daily[c + "USDT"]
            h = s[s.index < m0]
            r = np.log(h.iloc[-30:] / h.iloc[-30:].shift(1)).dropna()
            fr_rvs.append(r.std() * math.sqrt(365))
            fr_ret30.append(h.iloc[-1] / h.iloc[-31] - 1)
        fr_ret30 = np.array(fr_ret30)
        # BTC regime(B 的门:SMA100*1.03)
        hb = btc[btc.index < m0]
        sma100 = hb.iloc[-100:].mean()
        btc_regime = hb.iloc[-1] > sma100 * 1.03
        row = {
            "month": mstr, "n_adm": len(rvs),
            "rv_new_med": np.median(rvs) if rvs else np.nan,
            "rv_frozen_med": np.median(fr_rvs),
            "rv_ratio": (np.median(rvs) / np.median(fr_rvs)) if rvs else np.nan,
            "new_ret30_ew": np.mean(ret30s) if ret30s else np.nan,
            "new_above50_frac": np.mean(above50) if above50 else np.nan,
            "med_age_d": ages / len(rvs) if rvs else np.nan,
            "frzn_disp30": float(fr_ret30.std()),
            "frzn_ret30_ew": float(fr_ret30.mean()),
            "btc_regime_on": bool(btc_regime),
        }
        if mstr in pnl_open_month.index:
            row["newleg_pnl"] = float(pnl_open_month.loc[mstr, "pnl"])
            row["newleg_n"] = int(pnl_open_month.loc[mstr, "n"])
        else:
            row["newleg_pnl"], row["newleg_n"] = 0.0, 0
        rows.append(row)

    p = pd.DataFrame(rows).set_index("month")
    pd.set_option("display.width", 200)
    print("### 月度面板:门候选变量 × 新币腿 PnL(按开仓月)")
    print(p[["n_adm", "rv_new_med", "rv_frozen_med", "rv_ratio", "new_ret30_ew",
             "new_above50_frac", "med_age_d", "frzn_disp30", "btc_regime_on",
             "newleg_pnl", "newleg_n"]].to_string(float_format=lambda x: f"{x:7.3f}"))

    # --- 门控模拟 ---
    print("\n### 门控模拟(门 OFF → 删除该月开仓的新币腿交易;近似,忽略槽位二阶效应)")
    gates = {
        "G1 rv_ratio>=1.5": p["rv_ratio"] >= 1.5,
        "G1b rv_ratio>=2.0": p["rv_ratio"] >= 2.0,
        "G2 new_ret30_ew>0": p["new_ret30_ew"] > 0,
        "G2b new_above50_frac>=0.4": p["new_above50_frac"] >= 0.4,
        "G3 btc_regime_on": p["btc_regime_on"],
        "G4 frzn_disp30>=0.10": p["frzn_disp30"] >= 0.10,
        "G5 med_age_d<=400": p["med_age_d"] <= 400,
        "ALWAYS(=臂b)": pd.Series(True, index=p.index),
    }
    for name, on in gates.items():
        on = on.fillna(False)
        kept = p["newleg_pnl"].where(on, 0.0)
        byy = kept.groupby(p.index.str[:4]).sum()
        off24 = p.loc[(p.index.str[:4] == "2024") & ~on, "newleg_pnl"].sum()
        off2526 = p.loc[(p.index.str[:4].isin(["2025", "2026"])) & ~on,
                        "newleg_pnl"].sum()
        print(f"  {name:28s} ON月数={int(on.sum()):3d}/47 | "
              f"新币腿净额 24:{byy.get('2024',0):+8.0f} 25:{byy.get('2025',0):+8.0f} "
              f"26:{byy.get('2026',0):+8.0f} 23:{byy.get('2023',0):+8.0f} | "
              f"OFF拦掉的24亏损={-off24:+7.0f} 拦掉的25/26盈利={off2526:+7.0f}")

    # 组合门
    combo = (p["rv_ratio"] >= 1.5) & (p["new_above50_frac"] >= 0.4)
    kept = p["newleg_pnl"].where(combo, 0.0)
    byy = kept.groupby(p.index.str[:4]).sum()
    print(f"  {'C1 = G1&G2b':28s} ON月数={int(combo.sum()):3d}/47 | "
          f"新币腿净额 24:{byy.get('2024',0):+8.0f} 25:{byy.get('2025',0):+8.0f} "
          f"26:{byy.get('2026',0):+8.0f} 23:{byy.get('2023',0):+8.0f}")

    # 逐年相关:rv_ratio / ret30 与 newleg_pnl
    print("\n### 变量-月PnL 相关(2024 vs 2025/26 的区分度)")
    for col in ["rv_ratio", "new_ret30_ew", "new_above50_frac", "med_age_d",
                "frzn_disp30", "rv_frozen_med"]:
        v = p[col].astype(float)
        m24 = p.index.str[:4] == "2024"
        m56 = p.index.str[:4].isin(["2025", "2026"])
        print(f"  {col:20s} 2024均值={v[m24].mean():7.3f}  25/26均值={v[m56].mean():7.3f}  "
              f"2023均值={v[p.index.str[:4]=='2023'].mean():7.3f}")


if __name__ == "__main__":
    main()
