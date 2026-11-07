# -*- coding: utf-8 -*-
"""速度迁移假设验证 — 多尺度趋势质量 2021-2026 (research_revive/slowa)

假设: 趋势没死, 而是从 1h 尺度迁移到慢尺度 (4h/1d/1w); A 袖在 3h 事件尺度
上打空、付双倍保费 (交易数 49->94, 单笔均盈 14.7%->3.9% 权益)。

三个度量 (任务书指定):
  P1  variance ratio 谱: 基期 1h/4h/1d, horizon {1d,3d,7d,14d,30d,60d,90d}
      简单重叠 VR(q)=Var(r_q)/(q*Var(r_1)), 年度归属=收益结束时刻的年份。
      与 CONTEXT.md §5 的 VR30 (12币, 基期1d, q=30) 同口径对照。
  P2  Donchian 突破持续性: N∈{10,20,40,60}d 前高/前低突破 (close-to-close,
      首次突破事件), 持有 M∈{5,10,20,40}d 的期望收益/胜率, 逐年。
  P3  趋势段持续期: SMA50-of-bars 上方(且斜率>0)连续段, 尺度 1h/4h/1d/1w,
      逐年段数/中位段长/趋势态时间占比。

判定规则 (预注册在 report.md):
  慢尺度 (>=1d horizon) 的 2024-26 均值显著高于其 2021-23 均值, 或至少持平不降,
  且快尺度 (<=4h 事件尺度, 用 3h 重放 + VR 短 horizon) 明显衰减 -> 支持迁移;
  慢尺度同步衰减 -> 假设死。

输出: 打印 markdown 表格 (复制进 report.md), 并存 CSV 到本目录。
"""
import numpy as np
import pandas as pd

DATA = "/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures"
COINS = ["BTC", "ETH", "SOL"]
OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_revive/slowa"
YEARS = list(range(2021, 2027))


def load_1h(coin):
    df = pd.read_feather(f"{DATA}/{coin}_USDT_USDT-1h-futures.feather")
    df = df.set_index("date").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def resample_ohlc(df, rule):
    """UTC 对齐整 bin 重采样; 只保留完整 bin (末尾不完整 bin 由 freqtrade 数据
    本身完整性保证, 1h feather 全为整点, 末 bin 丢弃)。"""
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    v = df["volume"].resample(rule).sum()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}).dropna()
    return out


# ---------------------------------------------------------------- P1: VR 谱
def vr_q(logret: pd.Series, q: int) -> float:
    """简单重叠 variance ratio: Var(r_q)/(q*Var(r_1)), r 为对数收益。
    已知小样本向上偏差, 点估计口径, 与 CONTEXT.md VR30 同族(披露)。"""
    r = logret.dropna().to_numpy()
    n = len(r)
    if n < 4 * q:  # 至少 4 个非重叠观测
        return np.nan
    mu = r.mean()
    var1 = ((r - mu) ** 2).sum() / (n - 1)
    rq = np.convolve(r, np.ones(q), "valid")  # 长度 n-q+1, 重叠
    muq = rq.mean()
    varq = ((rq - muq) ** 2).sum() / (len(rq) - 1)
    return varq / (q * var1)


def vr_table():
    rows = []
    specs = [
        # (基期scale, horizon天, q)
        ("1h", 1, 24), ("1h", 3, 72), ("1h", 7, 168), ("1h", 14, 336), ("1h", 30, 720),
        ("4h", 1, 6), ("4h", 7, 42), ("4h", 14, 84), ("4h", 30, 180),
        ("1d", 1, 1), ("1d", 3, 3), ("1d", 7, 7), ("1d", 14, 14),
        ("1d", 30, 30), ("1d", 60, 60), ("1d", 90, 90),
    ]
    data = {c: load_1h(c) for c in COINS}
    for scale, hz, q in specs:
        rule = {"1h": "1h", "4h": "4h", "1d": "1D"}[scale]
        for coin in COINS:
            df = data[coin]
            if rule == "1h":
                bars = df
            else:
                bars = resample_ohlc(df, rule)
            lr = np.log(bars["close"]).diff()
            # 重叠 r_q 的年度归属: 结束时刻 = lr.index[q-1:], 用对齐索引
            ends = lr.index[q - 1:]
            vals = np.convolve(lr.to_numpy(), np.ones(q), "valid")
            rq_s = pd.Series(vals, index=ends)
            for y in YEARS:
                sub = rq_s[rq_s.index.year == y]
                if len(sub) < 4:
                    continue
                # 年内重算 VR: 用该年基期收益 + 重叠 q 收益
                base = lr[(lr.index.year == y)]
                # 边界: 年初的 q 收益跨年 — 用年初回看 q 根(归因保守: 归到结束年)
                vr = vr_q_year(lr, sub.index.min(), sub.index.max(), q)
                rows.append({"scale": scale, "horizon_d": hz, "coin": coin,
                             "year": y, "VR": vr, "n_q": len(sub)})
    t = pd.DataFrame(rows)
    t.to_csv(f"{OUT}/vr_by_coin.csv", index=False)
    # 3 币平均
    g = t.groupby(["scale", "horizon_d", "year"])["VR"].mean().reset_index()
    piv = g.pivot_table(index=["scale", "horizon_d"], columns="year", values="VR")
    piv["24-26均值"] = piv[[2024, 2025, 2026]].mean(axis=1)
    piv["21-23均值"] = piv[[2021, 2022, 2023]].mean(axis=1)
    piv["比值(24-26)/(21-23)"] = piv["24-26均值"] / piv["21-23均值"]
    return piv.round(3)


def vr_q_year(lr: pd.Series, t0, t1, q: int) -> float:
    """年内 VR: 基期收益从 t0 前 q 根开始(年初回看, 使 q 收益可比),
    重叠 q 收益只统计结束时刻落在 [t0, t1] 内的观测。"""
    base = lr.loc[:t1]
    i0 = lr.index.searchsorted(t0)
    base = base[base.index >= lr.index[max(i0 - q, 0)]]
    r = base.to_numpy()
    n = len(r)
    if n < 3 * q:
        return np.nan
    rq = np.convolve(r, np.ones(q), "valid")
    # 只保留结束时刻在 [t0,t1] 内的重叠观测
    endpos = base.index[q - 1:]
    mask = np.asarray((endpos >= t0) & (endpos <= t1))
    rq = rq[mask]
    if len(rq) < 4:
        return np.nan
    mu = r.mean()
    var1 = ((r - mu) ** 2).sum() / (n - 1)
    varq = ((rq - rq.mean()) ** 2).sum() / (len(rq) - 1)
    return varq / (q * var1)


# ---------------------------------------------------- P2: Donchian 突破事件
def breakout_table():
    rows = []
    for coin in COINS:
        d1 = resample_ohlc(load_1h(coin), "1D")
        c = d1["close"]
        for N in [10, 20, 40, 60]:
            ub = c.rolling(N).max().shift(1)
            lb = c.rolling(N).min().shift(1)
            up = c > ub
            dn = c < lb
            up_ev = up & ~up.shift(1, fill_value=False)
            dn_ev = dn & ~dn.shift(1, fill_value=False)
            for M in [5, 10, 20, 40]:
                fwd = c.shift(-M) / c - 1.0
                for name, ev, ret in [("up", up_ev, fwd), ("down", dn_ev, -fwd)]:
                    idx = ev.index[ev.to_numpy()]
                    for ts in idx:
                        rows.append({"coin": coin, "N": N, "M": M, "dir": name,
                                     "year": ts.year, "ret": ret.loc[ts]
                                     if pd.notna(ret.loc[ts]) else np.nan})
    t = pd.DataFrame(rows).dropna()
    t.to_csv(f"{OUT}/breakout_events.csv", index=False)
    g = (t.groupby(["N", "M", "year"])
         .agg(n=("ret", "size"), mean=("ret", "mean"),
              win=("ret", lambda x: (x > 0).mean()))
         .reset_index())
    g["ret_bp"] = (g["mean"] * 1e4).round(0)
    piv = g.pivot_table(index=["N", "M"], columns="year",
                        values=["n", "ret_bp", "win"])
    return g, piv


# ------------------------------------------------------ P3: 趋势段持续期
def trend_segments(closes: pd.Series, sma_n: int):
    """SMA(sma_n) 上方且 SMA 斜率>0 的连续段; 返回 [(start, end, len_bars)]。"""
    sma = closes.rolling(sma_n).mean()
    up = (closes > sma) & (sma > sma.shift(1))
    segs = []
    start = None
    for i in range(len(up)):
        if up.iloc[i]:
            if start is None:
                start = i
        else:
            if start is not None:
                segs.append((up.index[start], up.index[i - 1], i - start))
                start = None
    if start is not None:
        segs.append((up.index[start], up.index[-1], len(up) - start))
    return segs


def segment_table():
    rows = []
    for coin in COINS:
        df = load_1h(coin)
        for scale, rule in [("1h", "1h"), ("4h", "4h"), ("1d", "1D"), ("1w", "1W")]:
            bars = df if rule == "1h" else resample_ohlc(df, rule)
            segs = trend_segments(bars["close"], 50)
            for start, end, L in segs:
                # 年度归属: 段结束年
                rows.append({"coin": coin, "scale": scale, "year": end.year, "len": L,
                             "days": (end - start).total_seconds() / 86400})
    t = pd.DataFrame(rows)
    t.to_csv(f"{OUT}/trend_segments.csv", index=False)
    g = (t.groupby(["scale", "year"])
         .agg(n_seg=("len", "size"), med_len=("len", "median"),
              mean_len=("len", "mean"), med_days=("days", "median"),
              tot_bars=("len", "sum"))
         .reset_index())
    # 趋势态占比: tot_bars / 年内 bars
    bars_per_year = {"1h": 8760, "4h": 2190, "1d": 365, "1w": 52}
    g["occ_pct"] = (g["tot_bars"] / g["year"].map(bars_per_year) * 100).round(0)
    # 3 币汇总平均
    g2 = (t.groupby(["scale", "year"])
          .apply(lambda x: pd.Series({
              "n_seg/币": x.groupby("coin").size().mean(),
              "中位段长(bars)": x["len"].median(),
              "中位段长(天)": x["days"].median(),
              "趋势态占比%": 100 * x["len"].sum() / (len(x["coin"].unique()) * bars_per_year[x.name[0]]),
          }), include_groups=False).reset_index())
    return g2


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print("=" * 90)
    print("P1 多尺度 variance ratio (3币平均, 简单重叠口径, n>=4/q保守)")
    vr = vr_table()
    print(vr.to_string())
    vr.to_csv(f"{OUT}/vr_summary.csv")

    print("=" * 90)
    print("P2 Donchian 突破(N日close-to-close前高/前低, 首次事件)持有M日: 3币合并")
    g, piv = breakout_table()
    g.to_csv(f"{OUT}/breakout_summary.csv", index=False)
    # 展示 N=20/40 的行
    for N in [10, 20, 40, 60]:
        print(f"--- N={N} ---")
        sub = g[g["N"] == N].pivot_table(index="M", columns="year",
                                         values=["n", "ret_bp", "win"])
        print(sub.round(3).to_string())

    print("=" * 90)
    print("P3 趋势段 (SMA50-of-bars 上方且斜率>0), 3币平均")
    seg = segment_table()
    print(seg.round(1).to_string())
    seg.to_csv(f"{OUT}/segments_summary.csv", index=False)
