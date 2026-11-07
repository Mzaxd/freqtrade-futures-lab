"""uni2 可行性研究 — 2024 反向年诊断(只读已有回测 zip,不跑新回测)。

数据源:
  user_data/backtest_results/uni_oos_b.zip  (臂 b: 冻结12+新币点时门控)
  user_data/backtest_results/uni_oos_c.zip  (臂 c: 全点时)
  user_data/backtest_results/uni_full_a.zip (臂 a: 冻结12 恒等)

问题:2024 扩池为什么 -4.0pp(基线 +107.7)?亏在哪些币/月/机制。
"""
import json
import os
import sys
import zipfile

import pandas as pd

LAB = "/Users/caihaohan/Code/freqtrade-futures-lab"
ZIPS = {
    "a_frozen12": f"{LAB}/user_data/backtest_results/uni_full_a.zip",
    "b_ext": f"{LAB}/user_data/backtest_results/uni_oos_b.zip",
    "c_pit": f"{LAB}/user_data/backtest_results/uni_oos_c.zip",
}
FROZEN12 = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
            "LINK", "DOT", "LTC", "UNI"}


def load_trades(zip_path: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist()
                 if n.endswith(".json") and "config" not in n and "_wallet" not in n
                 and n.split("/")[-1].startswith("backtest-result")]
        assert len(names) == 1, names
        with z.open(names[0]) as f:
            d = json.load(f)
        skey = list(d["strategy"].keys())[0]
        tr = pd.DataFrame(d["strategy"][skey]["trades"])
    tr["open_date"] = pd.to_datetime(tr["open_date"], utc=True)
    tr["close_date"] = pd.to_datetime(tr["close_date"], utc=True)
    tr["year"] = tr["close_date"].dt.year
    tr["month"] = tr["close_date"].dt.strftime("%Y-%m")
    tr["base"] = tr["pair"].str.split("/").str[0]
    tr["is_frozen"] = tr["base"].isin(FROZEN12)
    tr["dir"] = tr["is_short"].map({True: "short", False: "long"})
    return tr


def gross(t: pd.DataFrame, mask) -> tuple[float, float, int, int]:
    """返回 (毛盈, 毛亏, 盈笔数, 亏笔数) 均为 profit_abs USDT 汇总。"""
    sub = t[mask]
    wins = sub[sub["profit_abs"] > 0]["profit_abs"]
    losses = sub[sub["profit_abs"] <= 0]["profit_abs"]
    return wins.sum(), losses.sum(), len(wins), len(losses)


def main():
    trs = {k: load_trades(v) for k, v in ZIPS.items()}

    print("=" * 78)
    print("### 1) 臂 b 逐年:冻结腿 vs 新币腿(USDT,开盘钱包7000)")
    b = trs["b_ext"]
    for y in [2023, 2024, 2025, 2026]:
        for leg in [True, False]:
            m = (b["year"] == y) & (b["is_frozen"] == leg)
            w, l, nw, nl = gross(b, m)
            sub = b[m]
            pf = w / abs(l) if l != 0 else float("inf")
            print(f"  {y} {'冻结12' if leg else '新币  '} net={sub['profit_abs'].sum():+9.0f} "
                  f"毛盈={w:+8.0f} 毛亏={l:+8.0f} PF={pf:5.2f} "
                  f"n={nw}+{nl} 胜率={nw/(nw+nl)*100:4.1f}% "
                  f"均笔={sub['profit_abs'].mean():+7.1f} "
                  f"均持h={sub['trade_duration'].mean()/60:6.1f}")

    print("\n### 2) 臂 b 2024 逐月:两腿净额")
    for m_ in sorted(b[b["year"] == 2024]["month"].unique()):
        row = [f"  {m_}"]
        for leg in [True, False]:
            m = (b["month"] == m_) & (b["is_frozen"] == leg)
            sub = b[m]
            row.append(f"{'冻结' if leg else '新币'} {sub['profit_abs'].sum():+7.0f} "
                       f"({len(sub)}笔)")
        print("  ".join(row))

    print("\n### 3) 臂 b 2024 新币腿:逐币(按净额排序,USDT)")
    n24 = b[(b["year"] == 2024) & (~b["is_frozen"])]
    per = n24.groupby("base").agg(
        net=("profit_abs", "sum"), n=("profit_abs", "size"),
        wins=("profit_abs", lambda s: int((s > 0).sum())),
        gross_win=("profit_abs", lambda s: s[s > 0].sum()),
        gross_loss=("profit_abs", lambda s: s[s <= 0].sum()),
        dur_h=("trade_duration", lambda s: s.mean() / 60),
    ).sort_values("net")
    print(per.to_string(float_format=lambda x: f"{x:8.1f}"))
    print(f"  新币 2024 合计 net={n24['profit_abs'].sum():+.0f},n={len(n24)}")
    print(f"  其中 top5 亏损币贡献 {per['net'].head(5).sum():+.0f}")

    print("\n### 4) 臂 b 2024 新币腿:方向×退出")
    g = n24.groupby(["dir", "exit_reason"]).agg(
        net=("profit_abs", "sum"), n=("profit_abs", "size")).sort_values("net")
    print(g.to_string(float_format=lambda x: f"{x:8.1f}"))

    print("\n### 5) 同窗对照:2024 冻结腿在臂 a(无新币抢槽)的表现")
    a = trs["a_frozen12"]
    for y in [2023, 2024, 2025, 2026]:
        m = a["year"] == y
        sub = a[m]
        w, l, nw, nl = gross(a, m)
        pf = w / abs(l) if l != 0 else float("inf")
        print(f"  a {y} 全部冻结12 net={sub['profit_abs'].sum():+9.0f} n={len(sub)} "
              f"PF={pf:5.2f}")
        mb = (b["year"] == y) & (b["is_frozen"])
        subb = b[mb]
        wb, lb, nwb, nlb = gross(b, mb)
        pfb = wb / abs(lb) if lb != 0 else float("inf")
        print(f"  b {y} 冻结12腿    net={subb['profit_abs'].sum():+9.0f} n={len(subb)} "
              f"PF={pfb:5.2f}   <- MOT 槽竞争下的冻结腿")

    print("\n### 6) 臂 b 2024:逐月毛盈/毛亏分解(全池)")
    for m_ in sorted(b[b["year"] == 2024]["month"].unique()):
        m = b["month"] == m_
        w, l, nw, nl = gross(b, m)
        pf = w / abs(l) if l != 0 else float("inf")
        print(f"  {m_} net={b[m]['profit_abs'].sum():+8.0f} 毛盈={w:+8.0f} "
              f"毛亏={l:+8.0f} PF={pf:5.2f} n={nw + nl}")

    print("\n### 7) 新币腿盈利集中度(23-26 全窗,USDT)")
    nall = b[~b["is_frozen"]]
    percoin = nall.groupby("base")["profit_abs"].sum().sort_values(ascending=False)
    tot = percoin.sum()
    print(f"  新币合计 {tot:+.0f}, 逐币 top10/bottom5:")
    print(percoin.head(10).to_string(float_format=lambda x: f"{x:+9.0f}"))
    print("  ...")
    print(percoin.tail(5).to_string(float_format=lambda x: f"{x:+9.0f}"))
    print(f"  ENA+MYX 占新币净利 = "
          f"{(percoin.get('ENA',0)+percoin.get('MYX',0))/tot*100:.0f}%")

    print("\n### 8) 新币腿逐年净额(23-26)与逐币 top3(每年)")
    for y in [2023, 2024, 2025, 2026]:
        sub = b[(b["year"] == y) & (~b["is_frozen"])]
        p = sub.groupby("base")["profit_abs"].sum().sort_values(ascending=False)
        top = ", ".join(f"{k}{v:+.0f}" for k, v in p.head(3).items())
        bot = ", ".join(f"{k}{v:+.0f}" for k, v in p.tail(3).items())
        print(f"  {y} 新币净={sub['profit_abs'].sum():+8.0f} n={len(sub):3d} "
              f"| top3: {top} | bottom3: {bot}")

    print("\n### 9) 2024 新币腿的持仓时长与止损率 vs 2025/26")
    for y in [2023, 2024, 2025, 2026]:
        sub = b[(b["year"] == y) & (~b["is_frozen"])]
        if not len(sub):
            continue
        sl = (sub["exit_reason"] == "stop_loss").mean() * 100
        tr_ = (sub["exit_reason"] == "trailing_stop_loss").mean() * 100
        print(f"  {y} n={len(sub):3d} 止损率={sl:4.1f}% 追踪止损率={tr_:4.1f}% "
              f"均笔净={sub['profit_abs'].mean():+7.1f} "
              f"均持h={sub['trade_duration'].mean()/60:6.1f} "
              f"中位持h={sub['trade_duration'].median()/60:6.1f}")

    print("\n### 10) 每年入场月的新币年龄(首根日线距今,诊断筛选滞后)")
    firsts = {}
    ddir = f"{LAB}/research_improve/uni/daily"
    for fn in os.listdir(ddir):
        if fn.endswith(".csv"):
            df = pd.read_csv(os.path.join(ddir, fn), nrows=1)
            firsts[fn[:-4]] = df["date"].iloc[0]
    for c in FROZEN12:
        firsts.pop(str(c) + "USDT", None)
    firsts = {k: pd.to_datetime(v, unit="ms", utc=True) for k, v in firsts.items()}
    ages = []
    for _, t in nall.iterrows():
        f0 = firsts.get(t["base"] + "USDT")
        if f0 is not None:
            ages.append((t["open_date"].year,
                         (t["open_date"] - f0).days, t["profit_abs"]))
    ag = pd.DataFrame(ages, columns=["year", "age_d", "pnl"])
    for y in [2023, 2024, 2025, 2026]:
        sub = ag[ag["year"] == y]
        if not len(sub):
            continue
        young = sub[sub["age_d"] < 180]
        old = sub[sub["age_d"] >= 180]
        print(f"  {y} 入场时龄<180d: n={len(young)} net={young['pnl'].sum():+8.0f} | "
              f"≥180d: n={len(old)} net={old['pnl'].sum():+8.0f}")

    print("\n### 11) 2024 新币腿亏损的时间聚集:单笔最大 12 笔")
    n24s = n24.nsmallest(12, "profit_abs")[
        ["base", "month", "dir", "open_date", "close_date", "profit_abs",
         "exit_reason", "trade_duration"]]
    print(n24s.to_string(index=False, float_format=lambda x: f"{x:8.1f}"))


if __name__ == "__main__":
    sys.exit(main())
