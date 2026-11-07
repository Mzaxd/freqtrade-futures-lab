"""uni2 — 补充:怪物月构成、年龄结构门、篮子回撤门、槽位竞争量化。"""
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


def load_trades(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist()
                 if n.endswith(".json") and "config" not in n
                 and n.split("/")[-1].startswith("backtest-result")]
        with z.open(names[0]) as f:
            d = json.load(f)
        tr = pd.DataFrame(d["strategy"][list(d["strategy"].keys())[0]]["trades"])
    tr["open_date"] = pd.to_datetime(tr["open_date"], utc=True)
    tr["close_date"] = pd.to_datetime(tr["close_date"], utc=True)
    tr["base"] = tr["pair"].str.split("/").str[0]
    tr["om"] = tr["open_date"].dt.strftime("%Y-%m")
    return tr


def main():
    tr = load_trades(f"{LAB}/user_data/backtest_results/uni_oos_b.zip")
    new = tr[~tr["base"].isin(FROZEN12)]

    print("### A) 怪物月构成(新币腿,按开仓月)")
    for m in ["2025-09", "2026-08", "2024-03", "2024-07", "2026-10"]:
        sub = new[new["om"] == m]
        per = sub.groupby("base")["profit_abs"].sum().sort_values(ascending=False)
        print(f"\n  {m} net={sub['profit_abs'].sum():+.0f} ({len(sub)}笔)")
        print("   ", per.to_dict())

    print("\n### B) ENA/MYX/币安人生/H 逐笔时间线(新币腿核心利润)")
    for b in ["ENA", "MYX", "H", "币安人生", "ARB", "ONDO"]:
        sub = new[new["base"] == b]
        if not len(sub):
            continue
        print(f"  {b}: net={sub['profit_abs'].sum():+.0f} "
              f"({len(sub)}笔,{sub['open_date'].min().date()}~{sub['open_date'].max().date()})")
        big = sub.nlargest(3, "profit_abs")[
            ["open_date", "close_date", "is_short", "profit_abs", "exit_reason",
             "trade_duration"]]
        print(big.to_string(index=False))

    # 年龄结构门:每月 admitted 且 age<=180d 的新币数(点时可算)
    ext = pd.read_csv(f"{UNI}/universe_ext.csv")
    ext["sym"] = ext["pair"].str.split("/").str[0] + "USDT"
    firsts = {}
    for fn in os.listdir(f"{UNI}/daily"):
        if fn.endswith(".csv"):
            df = pd.read_csv(f"{UNI}/daily/{fn}", nrows=1)
            firsts[fn[:-4]] = pd.to_datetime(df["date"].iloc[0], unit="ms", utc=True)
    months = pd.period_range("2023-01", "2026-11", freq="M")
    pnl_om = new.groupby("om")["profit_abs"].sum()
    print("\n### C) 新上市供给变量(每月):≤180d 在池数、≤365d 在池数(只用当月快照)")
    rows = []
    for month in months:
        m0 = month.to_timestamp(how="start").tz_localize("UTC")
        syms = ext.loc[ext["month"] == str(month), "sym"]
        n180 = n365 = 0
        for s in syms:
            f0 = firsts.get(s)
            if f0 is None:
                continue
            age = (m0 - f0).days
            if age <= 180:
                n180 += 1
            if age <= 365:
                n365 += 1
        rows.append({"month": str(month), "n_adm": len(syms), "n180": n180,
                     "n365": n365,
                     "pnl": float(pnl_om.get(str(month), 0.0))})
    ap = pd.DataFrame(rows).set_index("month")
    print(ap.to_string(float_format=lambda x: f"{x:7.1f}"))

    for thr in [1, 2, 3, 5]:
        on = ap["n180"] >= thr
        kept = ap["pnl"].where(on, 0.0)
        byy = kept.groupby(ap.index.str[:4]).sum()
        off24 = ap.loc[(ap.index.str[:4] == "2024") & ~on, "pnl"].sum()
        off56 = ap.loc[(ap.index.str[:4].isin(["2025", "2026"])) & ~on, "pnl"].sum()
        print(f"  门 n180>={thr}: ON={int(on.sum())}/47 | 23:{byy.get('2023',0):+7.0f} "
              f"24:{byy.get('2024',0):+7.0f} 25:{byy.get('2025',0):+7.0f} "
              f"26:{byy.get('2026',0):+7.0f} | 拦24亏={-off24:+6.0f} "
              f"拦25/26盈={off56:+6.0f}")

    # 篮子回撤门:EW 篮子(可回测新币,点时成员)/ 60d 高点
    daily = {}
    for fn in os.listdir(f"{UNI}/daily"):
        if not fn.endswith(".csv"):
            continue
        df = pd.read_csv(f"{UNI}/daily/{fn}")
        if len(df) < 10:
            continue
        idx = pd.to_datetime(df["date"].astype("int64"), unit="ms", utc=True)
        daily[fn[:-4]] = pd.Series(df["close"].astype(float).values, index=idx)
    active = {m: set(g["sym"]) for m, g in ext.groupby("month")}
    all_days = pd.date_range("2023-01-01", "2026-11-07", tz="UTC", freq="D")
    basket = []
    for d in all_days:
        mstr = f"{d.year}-{d.month:02d}"
        syms = active.get(mstr, set())
        rets = []
        for s in syms:
            ser = daily.get(s)
            if ser is None:
                continue
            h = ser[ser.index <= d].iloc[-31:]
            if len(h) >= 21:
                rets.append(h.iloc[-1] / h.iloc[0])
        basket.append({"date": d, "n": len(rets),
                       "idx": float(np.mean(rets)) if rets else np.nan})
    bk = pd.DataFrame(basket).set_index("date")
    bk["rollmax60"] = bk["idx"].rolling(60).max()
    bk["dd"] = bk["idx"] / bk["rollmax60"] - 1
    # 月初回撤(用上月末,严格因果)
    bk["ym"] = bk.index.strftime("%Y-%m")
    month_end_dd = bk.groupby("ym")["dd"].last().shift(1)
    print("\n### D) 新币篮子 60d 回撤门(月初取上月末回撤)")
    ddv = month_end_dd.reindex(ap.index)
    for thr in [-0.15, -0.20, -0.30]:
        on = ddv > thr
        on = on.fillna(True)
        kept = ap["pnl"].where(on, 0.0)
        byy = kept.groupby(ap.index.str[:4]).sum()
        off24 = ap.loc[(ap.index.str[:4] == "2024") & ~on, "pnl"].sum()
        off56 = ap.loc[(ap.index.str[:4].isin(["2025", "2026"])) & ~on, "pnl"].sum()
        print(f"  门 dd>{thr}: ON={int(on.sum())}/47 | 23:{byy.get('2023',0):+7.0f} "
              f"24:{byy.get('2024',0):+7.0f} 25:{byy.get('2025',0):+7.0f} "
              f"26:{byy.get('2026',0):+7.0f} | 拦24亏={-off24:+6.0f} "
              f"拦25/26盈={off56:+6.0f}")

    # 槽位竞争:2024 臂a vs 臂b 冻结腿交易数与净额(% 口径)
    print("\n### E) 槽位竞争(冻结腿,2024):")
    tra = load_trades(f"{LAB}/user_data/backtest_results/uni_full_a.zip")
    fra = tra[tra["base"].isin(FROZEN12)]
    # 臂a 钱包在 2024 初 ≈ 7000 * (1+1.595)(1+1.480)(1+1.185)
    wa24 = 7000 * 2.595 * 2.480 * 2.185
    frb = tr[tr["base"].isin(FROZEN12)]
    for y in [2023, 2024, 2025, 2026]:
        sa = fra[fra["open_date"].dt.year == y]["profit_abs"].sum()
        wa = wa24 if y >= 2024 else None
        nb = len(fra[fra["open_date"].dt.year == y])
        sb = frb[frb["open_date"].dt.year == y]["profit_abs"].sum()
        nbn = len(frb[frb["open_date"].dt.year == y])
        nn = len(new[new["open_date"].dt.year == y])
        print(f"  {y}: a冻结腿 {nb:3d}笔 {sa:+9.0f} | b冻结腿 {nbn:3d}笔 {sb:+8.0f} "
              f"| b新币腿 {nn:3d}笔 → 槽位被抢 {nb - nbn:3d}")


if __name__ == "__main__":
    main()
