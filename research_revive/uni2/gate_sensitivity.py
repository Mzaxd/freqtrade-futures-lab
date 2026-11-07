"""uni2 — 收尾:G4 离散度门阈值敏感性、2021-22 定标分布、月命中率统计。"""
import json
import zipfile

import numpy as np
import pandas as pd

LAB = "/Users/caihaohan/Code/freqtrade-futures-lab"
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
    tr["base"] = tr["pair"].str.split("/").str[0]
    tr["om"] = tr["open_date"].dt.strftime("%Y-%m")
    return tr


def main():
    # 冻结12 1d feather → 月度离散度(30d 收益横截面 std),2021-01..2026-11
    closes = {}
    for c in FROZEN12:
        fe = pd.read_feather(
            f"{LAB}/user_data/data/binance/futures/{c}_USDT_USDT-1d-futures.feather")
        idx = pd.DatetimeIndex(fe["date"])
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        closes[c] = pd.Series(fe["close"].astype(float).values, index=idx)

    months = pd.period_range("2021-01", "2026-11", freq="M")
    disp = {}
    corr = {}
    for month in months:
        m0 = month.to_timestamp(how="start").tz_localize("UTC")
        rets = {}
        for c, s in closes.items():
            h = s[s.index < m0]
            if len(h) >= 31:
                rets[c] = h.iloc[-1] / h.iloc[-31] - 1
        if len(rets) >= 8:
            disp[str(month)] = float(np.std(list(rets.values())))
        # 30d 日收益两两相关均值(简化:每币 30d 日收益序列)
        mat = {}
        for c, s in closes.items():
            h = s[s.index < m0].iloc[-31:]
            if len(h) >= 25:
                mat[c] = np.log(h / h.shift(1)).dropna()
        if len(mat) >= 8:
            cm = pd.DataFrame(mat).corr().values
            iu = np.triu_indices(len(mat), k=1)
            corr[str(month)] = float(cm[iu].mean())

    dp = pd.Series(disp)
    cp = pd.Series(corr)
    print("### 冻结12 月度离散度(30d收益横截面std)与币间相关(30d日收益):")
    byyr_d = dp.groupby(dp.index.str[:4]).agg(["mean", "min", "max"])
    byyr_c = cp.groupby(cp.index.str[:4]).agg(["mean", "min", "max"])
    print(byyr_d.round(3).to_string())
    print(byyr_c.round(3).to_string())
    q2122 = dp[dp.index.str[:4].isin(["2021", "2022"])]
    print(f"2021-22 分布: p10={q2122.quantile(0.1):.3f} p25={q2122.quantile(0.25):.3f} "
          f"median={q2122.median():.3f} p75={q2122.quantile(0.75):.3f}")
    q23 = dp[dp.index.str[:4] == "2023"]
    print(f"2023 分布: p10={q23.quantile(0.1):.3f} median={q23.median():.3f} "
          f"p75={q23.quantile(0.75):.3f}")

    tr = load_trades(f"{LAB}/user_data/backtest_results/uni_oos_b.zip")
    new = tr[~tr["base"].isin(FROZEN12)]
    pnl = new.groupby("om")["profit_abs"].sum()
    pnl = pnl.reindex([str(m) for m in pd.period_range("2023-01", "2026-11", freq="M")],
                      fill_value=0.0)

    print("\n### G4 阈值敏感性(disp>=thr 才 ON;23-26 新币腿净额 by 开仓月)")
    for thr in [0.06, 0.08, 0.09, 0.10, 0.12, 0.15, 0.20]:
        on = dp.reindex(pnl.index) >= thr
        kept = pnl.where(on, 0.0)
        byy = kept.groupby(pnl.index.str[:4]).sum()
        print(f"  thr={thr:.2f} ON={int(on.sum())}/47 | 23:{byy.get('2023',0):+7.0f} "
              f"24:{byy.get('2024',0):+7.0f} 25:{byy.get('2025',0):+7.0f} "
              f"26:{byy.get('2026',0):+7.0f} | 24-26合计:{byy.get('2024',0)+byy.get('2025',0)+byy.get('2026',0):+8.0f}")

    print("\n### 相关门( corr30 <= thr 才 ON)敏感性")
    for thr in [0.55, 0.60, 0.65, 0.70]:
        on = cp.reindex(pnl.index) <= thr
        kept = pnl.where(on, 0.0)
        byy = kept.groupby(pnl.index.str[:4]).sum()
        print(f"  corr<= {thr:.2f} ON={int(on.sum())}/47 | 23:{byy.get('2023',0):+7.0f} "
              f"24:{byy.get('2024',0):+7.0f} 25:{byy.get('2025',0):+7.0f} "
              f"26:{byy.get('2026',0):+7.0f} | 24-26合计:{byy.get('2024',0)+byy.get('2025',0)+byy.get('2026',0):+8.0f}")

    print("\n### 新币腿月命中率与偏度(按开仓月)")
    for y in ["2023", "2024", "2025", "2026"]:
        s = pnl[pnl.index.str[:4] == y]
        pos = (s > 0).sum()
        print(f"  {y}: +月={pos}/{len(s)} 均值={s.mean():+8.0f} 中位={s.median():+7.0f} "
              f"max={s.max():+8.0f} min={s.min():+8.0f} "
              f"top1月占年内总盈={s.max()}/{s[s>0].sum():.0f}={s.max()/max(s[s>0].sum(),1)*100:.0f}%")

    # 若剔除 ENA+MYX:月度序列
    ex = new[~new["base"].isin(["ENA", "MYX"])]
    pex = ex.groupby("om")["profit_abs"].sum().reindex(pnl.index, fill_value=0.0)
    print("\n### 剔除 ENA+MYX 后的新币腿(按开仓月,USDT):")
    for y in ["2023", "2024", "2025", "2026"]:
        s = pex[pex.index.str[:4] == y]
        print(f"  {y}: 净={s.sum():+8.0f} (+月={(s>0).sum()}/{len(s)})")


if __name__ == "__main__":
    main()
