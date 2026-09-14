# -*- coding: utf-8 -*-
"""XS-momentum 研究引擎（纯 pandas/numpy，组合语义与 freqtrade 单策略回测不同，故独立实现）。

按 PREREGISTRATION.md（v2）实现：
- 信号: mom = close[t-skip]/close[t-skip-lookback] - 1, lookback∈{7,14,30,60,90}, skip∈{0,1}
- 组合: 动量降序 top/bottom 组（各 ceil(0.2N)），LS/LO/SO，持有 H∈{1,5,10} 日, 再平衡日收盘调仓
- 成本: taker 0.1%/边 × 单边换手名义; funding 逐 8h 事件按持仓方向计, 缺失按 0
- 防前视: 信号 t 日收盘可知 -> t 日收盘调仓, 收益 t+1 起算; 持有期间权重随价格漂移
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SANDBOX = Path(__file__).resolve().parents[1]
DATADIR = SANDBOX / "userdir" / "data" / "binance" / "futures"

LOOKBACKS = [7, 14, 30, 60, 90]
SKIPS = [0, 1]
HOLDS = [1, 5, 10]
PORTFOLIOS = ["LS", "LO", "SO"]

FEE_PER_SIDE = 0.001  # taker 0.1% 每边（双边合计 0.2% 往返），对单边换手名义计费
MIN_ELIGIBLE = 10     # 可交易门槛：再平衡日合格币 < 10 -> 空仓


# ---------------------------------------------------------------- data loading

def pair_to_base(pair: str) -> str:
    return pair.split("/")[0].replace(":USDT", "").replace("-", "")


def _fpath(base: str, kind: str, tf: str) -> Path:
    return DATADIR / f"{base}_USDT_USDT-{tf}-{kind}.feather"


def load_close_volume(bases: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    closes, vols = {}, {}
    for b in bases:
        f = _fpath(b, "futures", "1d")
        df = pd.read_feather(f)
        df = df.set_index("date")
        closes[b] = df["close"]
        vols[b] = df["volume"]
    close = pd.DataFrame(closes).sort_index()
    vol = pd.DataFrame(vols).reindex(close.index)
    return close, vol


def load_funding_daily(bases: list[str], index: pd.DatetimeIndex) -> tuple[pd.DataFrame, list[str]]:
    """逐 8h 结算事件按日求和 -> 日 funding 率（多头支付口径）。缺失币按全 0 并返回名单。"""
    cols, missing = {}, []
    for b in bases:
        f = _fpath(b, "funding_rate", "1h")
        if not f.exists():
            missing.append(b)
            continue
        df = pd.read_feather(f)
        if len(df) == 0:
            missing.append(b)
            continue
        daily = df.set_index("date")["funding_rate"].resample("1D").sum()
        cols[b] = daily
    fund = pd.DataFrame(cols).reindex(index).fillna(0.0)
    # 没下到 funding 的币（以及存在但窗口内全空者保持 0）
    return fund, missing


# ---------------------------------------------------------------- signal

def momentum(close: pd.DataFrame, lookback: int, skip: int) -> pd.DataFrame:
    """t 日收盘可知的动量（无前视）：用 close[t-skip] 与 close[t-skip-lookback]。"""
    a = close.shift(skip)
    b = close.shift(skip + lookback)
    return a / b - 1.0


def eligible_mask(mom: pd.DataFrame, lookback: int, skip: int, close: pd.DataFrame) -> pd.DataFrame:
    """合格 = 动量非 NaN（蕴含 lookback+skip+1 根非 NaN 收盘）。"""
    return mom.notna()


# ---------------------------------------------------------------- simulation

@dataclass
class SimResult:
    daily: pd.Series          # 日净收益率（分数）
    metrics: dict
    n_rebalance: int
    n_flat_days: int          # 因 <10 合格而空仓的再平衡日数
    avg_leg_size: float       # 平均每组币数
    fee_total: float
    funding_total: float
    turnover_per_rebal: float  # 平均单次再平衡单边换手（占权益比例）


def _target_weights(mom_row: pd.Series, portfolio: str) -> tuple[pd.Series, int]:
    """合格币按动量降序：top 组前 ceil(0.2N)，bottom 组后 ceil(0.2N)。返回 (target weights, 合格数)。"""
    elig = mom_row.dropna()
    n = len(elig)
    if n < MIN_ELIGIBLE:
        return pd.Series(0.0, index=mom_row.index), n
    k = math.ceil(0.2 * n)
    ranked = elig.sort_values(ascending=False, kind="mergesort")
    top, bot = ranked.index[:k], ranked.index[-k:]
    w = pd.Series(0.0, index=mom_row.index)
    if portfolio == "LS":
        w[top] = 1.0 / k
        w[bot] = -1.0 / k
    elif portfolio == "LO":
        w[top] = 1.0 / k
    elif portfolio == "SO":
        w[bot] = -1.0 / k
    else:
        raise ValueError(portfolio)
    return w, n


def simulate(close: pd.DataFrame, ret: pd.DataFrame, mom: pd.DataFrame,
             funding: pd.DataFrame, portfolio: str, hold: int,
             start: str, end: str) -> SimResult:
    """窗口 [start, end) 独立仿真：窗口首日（若信号可用）为首个再平衡日，此后每 hold 日一次。"""
    idx = close.index
    tz = idx.tz
    w_start = idx.searchsorted(pd.Timestamp(start, tz=tz))
    w_end = idx.searchsorted(pd.Timestamp(end, tz=tz))
    win = idx[w_start:w_end]
    if len(win) < 20:
        raise ValueError("evaluation window too short")

    w_prev = pd.Series(0.0, index=close.columns)   # 上一收盘后持有的权重（占权益）
    daily, fee_total, fund_total = {}, 0.0, 0.0
    n_rebal, n_flat, leg_sizes, turn_overs = 0, 0, [], []

    for i, d in enumerate(win):
        r = ret.loc[d]
        r0 = r.fillna(0.0)                          # 停牌/缺口当日按 0（持仓冻结）并计入披露
        gross = float((w_prev * r0).sum())
        # funding PnL：正费率多头支付、空头收取 -> 统一为 -w*rate
        fund = float(-(w_prev * funding.loc[d]).sum())
        # 权重漂移（自融资：以权益为分母）
        drift_factor = np.where(r0.notna() & (r0 != 0.0), 1.0 + r0.values, 1.0)
        denom = 1.0 + gross
        if denom == 0.0:
            denom = 1e-12
        w_drift = (w_prev.values * drift_factor) / denom

        cost = 0.0
        if i % hold == 0:                            # 再平衡日：t 日收盘信号 -> 收盘调仓
            tw, n_elig = _target_weights(mom.loc[d], portfolio)
            if n_elig < MIN_ELIGIBLE:
                n_flat += 1
            n_rebal += 1
            k = math.ceil(0.2 * n_elig) if n_elig >= MIN_ELIGIBLE else 0
            if k:
                leg_sizes.append(k)
            delta = tw.values - w_drift
            cost = FEE_PER_SIDE * float(np.abs(delta).sum())
            turn_overs.append(float(np.abs(delta).sum()))
            w_prev = tw.copy()
        else:
            w_prev = pd.Series(w_drift, index=close.columns)

        fee_total += cost
        fund_total += fund
        daily[d] = gross + fund - cost

    s = pd.Series(daily).sort_index()
    return SimResult(s, metrics(s), n_rebal, n_flat,
                     float(np.mean(leg_sizes)) if leg_sizes else 0.0,
                     fee_total, fund_total,
                     float(np.mean(turn_overs)) if turn_overs else 0.0)


def metrics(daily: pd.Series) -> dict:
    r = daily.values
    n = len(r)
    if n < 2 or np.std(r, ddof=1) == 0:
        return dict(total=0.0, cagr=0.0, vol=0.0, sharpe=0.0, maxdd=0.0,
                    pf=float("inf") if r.sum() > 0 else 0.0, hit=np.mean(r > 0))
    eq = np.cumprod(1.0 + r)
    total = eq[-1] - 1.0
    years = n / 365.0
    cagr = (eq[-1]) ** (1.0 / years) - 1.0 if eq[-1] > 0 else -1.0
    vol = float(np.std(r, ddof=1) * math.sqrt(365.0))
    sharpe = float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(365.0))
    peak = np.maximum.accumulate(eq)
    maxdd = float(((eq - peak) / peak).min())
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = float(gains / losses) if losses > 0 else float("inf")
    hit = float(np.mean(r > 0))
    return dict(total=float(total), cagr=float(cagr), vol=vol, sharpe=sharpe,
                maxdd=maxdd, pf=pf, hit=hit)


# ---------------------------------------------------------------- grid runner

def run_grid(close: pd.DataFrame, funding: pd.DataFrame,
             window: tuple[str, str], label: str) -> pd.DataFrame:
    ret = close.pct_change()
    rows = []
    daily_store: dict[str, pd.Series] = {}
    for lb in LOOKBACKS:
        for sk in SKIPS:
            mom = momentum(close, lb, sk)
            for h in HOLDS:
                for pf_ in PORTFOLIOS:
                    res = simulate(close, ret, mom, funding, pf_, h, window[0], window[1])
                    key = f"lb{lb}_sk{sk}_h{h}_{pf_}"
                    daily_store[key] = res.daily
                    rows.append(dict(key=key, lookback=lb, skip=sk, hold=h, portfolio=pf_,
                                     **res.metrics,
                                     n_rebal=res.n_rebalance, n_flat_days=res.n_flat_days,
                                     avg_leg=res.avg_leg_size, fee_total=res.fee_total,
                                     funding_total=res.funding_total,
                                     turnover_per_rebal=res.turnover_per_rebal))
    grid = pd.DataFrame(rows)
    outdir = SANDBOX / "results"
    grid.to_csv(outdir / f"grid_{label}.csv", index=False)
    pd.DataFrame(daily_store).to_csv(outdir / f"daily_{label}.csv")
    return grid


def run_single(close: pd.DataFrame, funding: pd.DataFrame, lb: int, sk: int, h: int,
               window: tuple[str, str], label: str) -> dict:
    ret = close.pct_change()
    mom = momentum(close, lb, sk)
    store = {}
    summary = []
    for pf_ in PORTFOLIOS:
        res = simulate(close, ret, mom, funding, pf_, h, window[0], window[1])
        store[pf_] = res.daily
        summary.append(dict(portfolio=pf_, **res.metrics,
                            n_rebal=res.n_rebalance, n_flat_days=res.n_flat_days,
                            avg_leg=res.avg_leg_size, fee_total=res.fee_total,
                            funding_total=res.funding_total,
                            turnover_per_rebal=res.turnover_per_rebal))
    outdir = SANDBOX / "results"
    pd.DataFrame(store).to_csv(outdir / f"daily_{label}.csv")
    return summary


def main():
    uni = json.load(open(SANDBOX / "universe_frozen_v2.json", encoding="utf-8"))
    bases = [pair_to_base(u["symbol"]) for u in uni["top40"]]
    close, _ = load_close_volume(bases)
    # 评估纪律：一切切片 ≤ 2023-12-31
    tz = close.index.tz
    close = close[close.index < pd.Timestamp("2024-01-01", tz=tz)]
    funding, missing = load_funding_daily(bases, close.index)
    print(f"universe={len(bases)} days={len(close)} range={close.index.min()}->{close.index.max()}")
    print(f"funding missing coins: {missing}")
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "is"
    if mode == "is":
        grid = run_grid(close, funding, ("2021-01-01", "2023-01-01"), "is")
        print(grid[grid.portfolio == "LS"].sort_values("sharpe", ascending=False).head(10).to_string())
    elif mode == "val":
        lb, sk, h = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
        summary = run_single(close, funding, lb, sk, h, ("2023-01-01", "2024-01-01"), "val")
        for s in summary:
            print(s)


if __name__ == "__main__":
    main()
