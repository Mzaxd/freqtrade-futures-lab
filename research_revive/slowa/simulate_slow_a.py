# -*- coding: utf-8 -*-
"""慢A信号级模拟器 — A 结构多尺度直译 (research_revive/slowa)

复刻冻结 A 袖 (ARL_2x = OPT9_Recycle RECYCLE_MULT=1.21, lev2) 的全部结构,
仅改变 resample bar 尺度:
  S3h  = 校验基准 (A 原生 3h 事件尺度, 应大致复现 A 袖逐年量级)
  S12h / S24h / S72h = 结构直译 (signal=stop=2.0xATR14 不变, ATR14 在 resample
      bar 上计算, atr08 门窗口 30 天按 bar 换算, 60d 时间止损, P2 全局同向熔断,
      recycle x1.21)
  D20_10 = Donchian 参照 (1d bar: 20d 前高/前低突破入场, 反向 10d 通道退出,
      2xATR14_d 锚定止损, 60d 时间止损, 同 sizing/同熔断/同 recycle)

与 freqtrade 的已知偏差 (全部披露, 影响量级见 report):
  - 信号在 resample bar 收盘可知, 成交在下一 resample bar 开盘 (freqtrade 是
    下一 1h bar 开盘; 对慢 bar 平均延迟 R/2 小时, 偏保守)
  - bar 内先查止损 (含 gap 以 open 成交) 再执行收盘信号; 时间止损以收盘价
  - 无 funding、无滑点; 费 taker 0.05% x notional 双边
  - 杠杆 2x 不入 PnL (PnL 中性已证), 直接用 notional 盈亏
  - 2026 年末未平仓以最后 bar 收盘强平并标注

输出: 逐年表 (收益%/笔数/胜率/PF/均笔盈亏 equity%/持仓中位 h) + 月度收益 CSV。
"""
import json
import sys

import numpy as np
import pandas as pd

DATA = "/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures"
COINS = ["BTC", "ETH", "SOL"]
OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_revive/slowa"

RISK = 0.01
SIG_MULT = 2.0
STOP_MULT = 2.0
STOP_FLOOR = 0.005
FEE_RT = 0.001           # 0.05% x 2 taker
TIME_STOP_H = 24 * 60
GATE_MULT = 0.8
GATE_WIN_D = 30
RECYCLE_MULT = 1.21
P2_N, P2_WIN_H, P2_BLOCK_H = 2, 24, 48


def load_bars(coin, rule_hours):
    df = pd.read_feather(f"{DATA}/{coin}_USDT_USDT-1h-futures.feather")
    df = df.set_index("date").sort_index()
    rule = f"{rule_hours}h"   # 24h 与 1D 的 UTC bin 边界一致; 72h 必须是 72h
    if rule_hours == 1:
        return df[["open", "high", "low", "close"]].copy()
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    return out


def atr14(bars):
    h, l, c = bars["high"], bars["low"], bars["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    # Wilder ATR 14
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return atr


def recycle_series(btc_bars_1h):
    """BTC 日线 close <= SMA100(已收盘天) -> True, 映射到 1h 网格。
    与 OPT9_Recycle._recycle_series 同义: recycle_on == NOT B.risk_on。"""
    d = btc_bars_1h["close"].resample("1D").last()
    sma = d.rolling(100).mean()
    on = (d <= sma) & sma.notna() & d.notna()
    # 天 D 的状态适用于 [D+1, D+2) 的 1h (该天收盘后才可知)
    on_1h = on.shift(1)
    on_1h.index = on_1h.index + pd.Timedelta(days=1)
    return on_1h.reindex(btc_bars_1h.index, method="ffill").fillna(False)


def run_sleeve(variant, start="2021-01-01", end="2026-11-07"):
    """事件驱动模拟。bars 网格 = 各 variant 的 resample bar; 统一换算到小时
    时长用于时间止损/熔断窗口。"""
    cfg = {
        "S3h": dict(kind="atr", R=3),
        "S12h": dict(kind="atr", R=12),
        "S24h": dict(kind="atr", R=24),
        "S72h": dict(kind="atr", R=72),
        "D20_10": dict(kind="donchian", R=24, N=20, X=10),
    }[variant]

    R = cfg["R"]
    bars = {c: load_bars(c, R) for c in COINS}
    btc1h = load_bars("BTC", 1)
    rec = recycle_series(btc1h)

    # 预计算信号列
    sig = {}
    for c in COINS:
        b = bars[c]
        a = atr14(b)
        cc = b["close"].diff()
        thr = a.shift(1) * SIG_MULT
        long_sig = cc > thr
        short_sig = -cc > thr
        gate_win = max(int(GATE_WIN_D * 24 / R), 2)
        gate_min = max(int(7 * 24 / R), 2)
        gate = (a >= GATE_MULT * a.rolling(gate_win, min_periods=gate_min).median()).fillna(False)
        entry = {}
        if cfg["kind"] == "atr":
            entry["long"] = long_sig & gate
            entry["short"] = short_sig & gate
        else:
            N, X = cfg["N"], cfg["X"]
            ub = b["close"].rolling(N).max().shift(1)
            lb = b["close"].rolling(N).min().shift(1)
            entry["long"] = (b["close"] > ub) & gate
            entry["short"] = (b["close"] < lb) & gate
        exit_long = short_sig     # 反向双ATR信号 (Donchian 变体用反向通道)
        exit_short = long_sig
        if cfg["kind"] == "donchian":
            xl = b["close"] < b["close"].rolling(X).min().shift(1)
            xs = b["close"] > b["close"].rolling(X).max().shift(1)
            exit_long, exit_short = xl, xs
        sig[c] = dict(atr=a, entry=entry, exit_long=exit_long,
                      exit_short=exit_short, bars=b)

    # 统一时间轴: 用最小 R 的 bar 网格推进 (3h), 信号只在所属 bar 收盘时刻生效
    grid = bars[COINS[0]].index
    for c in COINS[1:]:
        grid = grid.union(bars[c].index)
    grid = grid[(grid >= pd.Timestamp(start, tz="UTC"))
                & (grid <= pd.Timestamp(end, tz="UTC"))]

    eq = 1.0
    pos = {}          # coin -> dict(side, entry_px, notional, stop_px, entry_t, atr_e)
    trades = []
    stop_log = []     # (close_time_h_epoch, side) 用于 P2

    def bar_of(coin, t):
        b = sig[coin]["bars"]
        if t in b.index:
            return t
        return None

    # 逐 grid 时刻推进 (该时刻 = 某 coin 的 bar 收盘时刻)
    # 为效率: 预生成每 coin 的 bar 收盘事件序列
    events = []
    for c in COINS:
        b = sig[c]["bars"]
        for t in b.index[(b.index >= grid[0] - pd.Timedelta(hours=R)) & (b.index <= grid[-1])]:
            events.append((t, c))
    events.sort()

    for t, c in events:
        s = sig[c]
        b = s["bars"]
        i = b.index.get_loc(t)
        row = b.iloc[i]
        nxt = b.iloc[i + 1] if i + 1 < len(b) else None
        close_t = t

        # ---- 1) 管理持仓: bar i 的 low/high 查止损; 收盘信号; 时间止损
        if c in pos:
            p = pos[c]
            stop_hit = False
            exit_px, reason = None, None
            if p["side"] == 1:
                if row["low"] <= p["stop_px"]:
                    stop_hit = True
                    exit_px = min(row["open"], p["stop_px"])
                    reason = "stop"
            else:
                if row["high"] >= p["stop_px"]:
                    stop_hit = True
                    exit_px = max(row["open"], p["stop_px"])
                    reason = "stop"
            if not stop_hit:
                held_h = (close_t - p["entry_t"]).total_seconds() / 3600
                if s["exit_long"].iloc[i] if p["side"] == 1 else s["exit_short"].iloc[i]:
                    # 下一 bar 开盘平仓 (若有); 否则以本 bar 收盘
                    exit_px = nxt["open"] if nxt is not None else row["close"]
                    reason = "rev"
                    if nxt is not None:
                        close_t = b.index[i + 1]
                elif held_h >= TIME_STOP_H:
                    exit_px = row["close"]
                    reason = "time"
            if exit_px is not None:
                d = p["side"] * (exit_px / p["entry_px"] - 1)
                pnl = p["notional"] * d - p["notional"] * FEE_RT
                eq += pnl
                trades.append(dict(coin=c, side=p["side"], open=str(p["entry_t"]),
                                   close=str(close_t), held_h=(close_t - p["entry_t"]).total_seconds() / 3600,
                                   pnl_eq=pnl / p["eq0"], reason=reason))
                if reason == "stop":
                    stop_log.append((close_t, p["side"]))
                del pos[c]

        # ---- 2) 新信号 (bar i 收盘) -> 下一 bar 开盘入场
        if nxt is None or c in pos:
            continue
        a = s["atr"].iloc[i]
        if not np.isfinite(a) or a <= 0:
            continue
        side = 0
        if s["entry"]["long"].iloc[i]:
            side = 1
        elif s["entry"]["short"].iloc[i]:
            side = -1
        if side == 0:
            continue
        # P2 熔断: 24h 内 >=2 笔同向止损 -> 48h 内禁同向新仓
        if stop_log:
            recent = [ct for ct, sd in stop_log
                      if sd == side and (close_t - ct).total_seconds() / 3600 <= P2_WIN_H]
            if len(recent) >= P2_N:
                last = max(recent)
                if (close_t - last).total_seconds() / 3600 <= P2_BLOCK_H:
                    continue
        entry_px = nxt["open"]
        stop_px = entry_px - side * STOP_MULT * a
        stop_pct = max(STOP_MULT * a / entry_px, STOP_FLOOR)
        notional = eq * RISK / stop_pct
        if rec.reindex([close_t], method="ffill").iloc[0]:
            notional *= RECYCLE_MULT
        pos[c] = dict(side=side, entry_px=float(entry_px), notional=notional,
                      stop_px=float(stop_px), entry_t=b.index[i + 1], atr_e=a, eq0=eq)

    # 末尾强平
    for c, p in list(pos.items()):
        b = sig[c]["bars"]
        exit_px = b["close"].iloc[-1]
        d = p["side"] * (exit_px / p["entry_px"] - 1)
        pnl = p["notional"] * d - p["notional"] * FEE_RT
        eq += pnl
        trades.append(dict(coin=c, side=p["side"], open=str(p["entry_t"]),
                           close=str(b.index[-1]), held_h=(b.index[-1] - p["entry_t"]).total_seconds() / 3600,
                           pnl_eq=pnl / p["eq0"], reason="force"))
        del pos[c]

    tr = pd.DataFrame(trades)
    tr["year"] = pd.to_datetime(tr["close"]).dt.year
    tr["month"] = pd.to_datetime(tr["close"]).dt.to_period("M").astype(str)

    # 组合 equity 曲线 (逐笔累计) -> 逐年/月度
    tr = tr.sort_values("close").reset_index(drop=True)
    tr["eq_after"] = tr["pnl_eq"].cumsum() + 1.0
    rows = []
    eq_start = 1.0
    for y, g in tr.groupby("year"):
        pnl_y = g["pnl_eq"].sum()
        rows.append(dict(year=y, ret_eq=pnl_y / eq_start * 100, n=len(g),
                         win=100 * (g["pnl_eq"] > 0).mean(),
                         pf=g.loc[g["pnl_eq"] > 0, "pnl_eq"].sum()
                            / max(-g.loc[g["pnl_eq"] < 0, "pnl_eq"].sum(), 1e-12),
                         avg_win=g.loc[g["pnl_eq"] > 0, "pnl_eq"].mean() * 100,
                         avg_loss=g.loc[g["pnl_eq"] < 0, "pnl_eq"].mean() * 100,
                         med_hold_h=g["held_h"].median()))
        eq_start = g["eq_after"].iloc[-1]
    yearly = pd.DataFrame(rows)
    monthly = tr.groupby("month")["pnl_eq"].sum().reset_index()
    return yearly, monthly, tr


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    results = {}
    for v in ["S3h", "S12h", "S24h", "S72h", "D20_10"]:
        yearly, monthly, tr = run_sleeve(v)
        results[v] = dict(yearly=yearly, monthly=monthly, trades=tr)
        yearly.to_csv(f"{OUT}/sim_{v}_yearly.csv", index=False)
        monthly.to_csv(f"{OUT}/sim_{v}_monthly.csv", index=False)
        tr.to_csv(f"{OUT}/sim_{v}_trades.csv", index=False)
        print("=" * 100)
        print(f"变体 {v}  (逐年 ret 为年初权益百分比, avg_win/loss 为 equity%)")
        print(yearly.round(1).to_string(index=False))
        print(f"  总笔数 {len(tr)}; 总收益 {(tr['pnl_eq'].sum())*100:.0f}% (简单加总口径)")
