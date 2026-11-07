"""方案4 立项可行性复算:C2 智能网格作为独立副引擎(资金隔离、不进 AB 组合)。

纯 pandas 复算已有产物(research_chop/logs/grid_{episodes,summary}_{IS,OS}.csv 与
user_data/logs/mtm_daily_{A3,B3}.csv),不跑任何新回测、不重放模拟器(本地 5m feather
仅覆盖 2020-10~2023-12,C2 的 OS 模拟产物 CSV 已冻结留存,直接消费)。

Sections
  A. OS 选中配置(g2/L12/k0.5/dual/cross)净期望重算与集中度/年度/月度分解
  B. 独立副引擎口径敏感性:费用倍数、清仓滑点(费用恒等式近似清仓名义)、悲观集中度口径
  C. 与 A3/B3 的月度相关(点估计 + Fisher 95% CI)
  D. 容量:IS 期崩盘窗口 5m bar 名义 vs 10x 资金后的层名义/清仓名义(半定量)

Run:  .venv/bin/python -I research_revive/grid/recalc_side_engine.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CHOP_LOGS = ROOT / "research_chop" / "logs"
TAKER = 0.0005
INIT_EQ = 10_000.0
L = 12
OS_YEARS = (pd.Timestamp("2024-01-01") - pd.Timestamp("2026-09-12")).days / -365.25  # 2.704y
CAPITAL = 3 * INIT_EQ  # 30k isolated engine capital


def banner(s: str) -> None:
    print(f"\n{'=' * 78}\n{s}\n{'=' * 78}")


def load_os() -> pd.DataFrame:
    ep = pd.read_csv(CHOP_LOGS / "grid_episodes_OS.csv", parse_dates=["t_start", "t_end"])
    win = ep[(ep.gate == "g2") & (ep["L"] == 12) & (ep.k == 0.5)
             & (ep["mode"] == "dual") & (ep["fill"] == "cross")].copy()
    win["pnl"] = win.end_equity - win.start_equity
    return win.reset_index(drop=True)


# --------------------------------------------------------------------------- A
def section_a(win: pd.DataFrame) -> dict:
    banner("A. OS 选中配置总量复核(独立副引擎口径:30k 专属资金,年化按全额资金)")
    tot = dict(
        net=win.pnl.sum(), grid=win.grid_profit.sum(), clear=win.clear_pnl.sum(),
        fees=win.fees.sum(), funding=win.funding.sum(), n_ep=len(win),
        n_liq=int(win.n_liq.sum()), n_rt=int(win.n_rt.sum()), n_fills=int(win.n_fills.sum()),
    )
    print(f"net={tot['net']:+.0f}  grid={tot['grid']:+.0f}  clear={tot['clear']:+.0f}  "
          f"fees={tot['fees']:.0f}  funding={tot['funding']:+.0f}  eps={tot['n_ep']}  "
          f"liq={tot['n_liq']}  rt={tot['n_rt']}  fills={tot['n_fills']}")
    assert abs(tot["net"] - 3800) < 5, "frozen OS net must reproduce ~+3800"
    ann_simple = tot["net"] / CAPITAL / OS_YEARS * 100
    ann_cagr = ((1 + tot["net"] / CAPITAL) ** (1 / OS_YEARS) - 1) * 100
    print(f"OS {OS_YEARS:.3f}y on 30k: total {tot['net']/CAPITAL*100:+.2f}%  "
          f"annualized simple {ann_simple:+.2f}%/y  CAGR {ann_cagr:+.2f}%/y")

    print("\n-- top-5 episodes by pnl (集中度) --")
    top5 = win.nlargest(5, "pnl")
    print(top5[["pair", "t_start", "t_end", "pnl", "grid_profit", "clear_pnl", "fees"]]
          .assign(pnl=lambda d: d.pnl.round(0)).to_string(index=False))
    top5_sum = top5.pnl.sum()
    rest = win.drop(top5.index)
    print(f"top5 pnl sum {top5_sum:+.0f} ({top5_sum/tot['net']*100:.0f}% of net)   "
          f"other {len(rest)} eps sum {rest.pnl.sum():+.0f}  "
          f"(their grid {rest.grid_profit.sum():+.0f}, clear {rest.clear_pnl.sum():+.0f}, "
          f"fees {rest.fees.sum():.0f})")

    print("\n-- 年度分解 (by t_end) --")
    yr = win.assign(yr=win.t_end.dt.year).groupby("yr").agg(
        pnl=("pnl", "sum"), grid=("grid_profit", "sum"), clear=("clear_pnl", "sum"),
        fees=("fees", "sum"), n_ep=("pnl", "size"))
    yr["ann_pct_on_30k"] = yr.pnl / CAPITAL * 100
    print(yr.round(0).to_string())

    print("\n-- 月度序列 (干净月度聚合:to_period(M);冻结 xcheck 用 MonthEnd(0) 保留时刻,仅 17 个月偶然对齐,见报告披露) --")
    win["month"] = win.t_end.dt.to_period("M")
    m = win.groupby("month")["pnl"].sum()
    print(f"months with episodes={len(m)}  pos-months={int((m > 0).mean() * 100)}%  "
          f"best {m.max():+.0f} ({m.idxmax()})  worst {m.min():+.0f} ({m.idxmin()})")
    r12 = m.rolling(12).sum().min()
    print(f"worst rolling-12m PnL: {r12:+.0f} USD ({r12/CAPITAL*100:+.1f}% on 30k)")
    print("monthly PnL (USD):")
    print(m.round(0).to_string())
    burst_months = [p for p in m.index if str(p) in ("2024-03", "2024-04", "2025-01", "2025-02")]
    bm = m[m.index.isin(burst_months)]
    print(f"爆发 4 月({', '.join(map(str, burst_months))}) 合计 {bm.sum():+.0f} USD; "
          f"其余 {len(m)-len(bm)} 个月合计 {m.sum()-bm.sum():+.0f} USD")

    for label, lo, hi in [
        ("出血窗 2026-02-15..08-10", "2026-02-15", "2026-08-10"),
        ("下降通道 2025-10-01..2026-06-30", "2025-10-01", "2026-06-30"),
    ]:
        b = win[(win.t_end >= lo) & (win.t_end <= hi)]
        print(f"{label}: eps={len(b)} net={b.pnl.sum():+.0f} "
              f"(grid {b.grid_profit.sum():+.0f}, clear {b.clear_pnl.sum():+.0f}, "
              f"fees {b.fees.sum():.0f})  -> 年化 {b.pnl.sum()/CAPITAL/(pd.Timestamp(hi)-pd.Timestamp(lo)).days*365.25*100:+.1f}%")

    # 合并权益曲线(按段末推进,三币各持各自权益;段内更深未计——冻结披露 11)
    ev = []
    eq = {p: INIT_EQ for p in ("BTC", "ETH", "SOL")}
    for _, r in win.sort_values("t_end").iterrows():
        eq[r.pair] = r.end_equity
        ev.append((r.t_end, sum(eq.values())))
    curve = pd.Series(dict(ev)).sort_index()
    dd = (curve / curve.cummax() - 1).min()
    per_coin_dd = {}
    for p in ("BTC", "ETH", "SOL"):
        c = win[win.pair == p].set_index("t_end")["end_equity"].sort_index()
        c = pd.concat([pd.Series([INIT_EQ], index=[c.index.min() - pd.Timedelta(hours=1)]), c])
        per_coin_dd[p] = (c / c.cummax() - 1).min()
    print(f"\nengine equity curve (3x10k, episode-end marks): maxDD {dd*100:.1f}%   "
      f"per-coin { {p: f'{v*100:.1f}%' for p, v in per_coin_dd.items()} }")
    return dict(tot=tot, m=m, top5=top5, curve=curve, engine_dd=dd)


# --------------------------------------------------------------------------- B
def section_b(win: pd.DataFrame, tot: dict) -> dict:
    banner("B. 独立副引擎口径敏感性")
    # B1 费用倍数重放(段级复利顺序保留)
    def replay(fee_mult: float, clear_slip_bp: float = 0.0, clear_notional: pd.Series | None = None):
        eqs = {p: INIT_EQ for p in ("BTC", "ETH", "SOL")}
        for _, r in win.iterrows():  # win 保持 CSV(时间)顺序
            extra = (fee_mult - 1.0) * r.fees
            if clear_slip_bp and clear_notional is not None:
                extra += clear_slip_bp / 1e4 * clear_notional.loc[r.name]
            eqs[r.pair] += r.pnl - extra
        return sum(eqs.values()) - CAPITAL

    base = replay(1.0)
    print(f"replay check(费用=1x, 无滑点): {base:+.0f} (须≈+3800)")
    rows = []
    for mult in (0.4, 1.0, 1.25, 1.5, 2.0):  # 0.4 ≈ 全 maker(0.02%) 方向性参照
        net = replay(mult)
        rows.append((f"费用×{mult}", net, net / CAPITAL / OS_YEARS * 100))
    print("(滑点=0)  口径            净USD      年化% on 30k")
    for n, v, a in rows:
        print(f"          {n:<14} {v:+8.0f}   {a:+6.2f}")

    # B2 清仓名义近似(费用恒等式):每 fill 名义 ≈ 2*eq0/L * (px/anchor) ≈ 2*eq0/L
    win["fill_notional_est"] = 2 * win.start_equity / L
    win["fill_fees_est"] = TAKER * win.fill_notional_est * win.n_fills
    win["clear_fees_est"] = (win.fees - win.fill_fees_est).clip(lower=0)
    win["clear_notional_est"] = win.clear_fees_est / TAKER
    cn = win.clear_notional_est
    print(f"\n清仓名义近似: 合计 {cn.sum()/1e6:.2f} M USD / {int((cn>1).sum())} 个有库存清算段"
          f"（中位 {cn[cn>1].median():.0f}、最大单段 {cn.max():.0f} USD、p95 {cn[cn>1].quantile(.95):.0f}）")
    print(f"交叉验证: fill费用近似 {win.fill_fees_est.sum():.0f} vs 总费用 {tot['fees']:.0f}"
          f" -> 清仓费占比 {(1 - win.fill_fees_est.sum()/tot['fees'])*100:.0f}%（近似,层内 px/anchor 漂移 ±~10%）")
    big = win.nlargest(3, "clear_notional_est")[["pair", "t_end", "clear_pnl", "clear_notional_est", "max_net_expo"]]
    print("最大 3 笔集中清仓(名义近似):")
    print(big.assign(clear_notional_est=lambda d: d.clear_notional_est.round(0)).to_string(index=False))

    print("\n(费用=1x 加清仓滑点)  滑点bp    净USD      年化%")
    for bp in (5, 10, 15, 20):
        net = replay(1.0, bp, win.clear_notional_est)
        print(f"          {bp:>6}     {net:+8.0f}   {net/CAPITAL/OS_YEARS*100:+6.2f}")
    print("\n组合口径(费用×1.25 且 清仓滑点10bp；maker 化(×0.4) 且 5bp——两头):")
    for mult, bp in ((1.25, 10), (0.4, 5), (1.25, 15)):
        net = replay(mult, bp, win.clear_notional_est)
        print(f"          费用×{mult},滑点{bp}bp -> {net:+8.0f}  ({net/CAPITAL/OS_YEARS*100:+6.2f}%/y)")

    # B3 悲观集中度口径
    top5_sum = win.nlargest(5, "pnl").pnl.sum()
    rest_net = win.pnl.sum() - top5_sum
    print(f"\n悲观口径 P1(常态运行=非 top5 的 {len(win)-5} 段): 净 {rest_net:+.0f} USD "
          f"-> 年化 {rest_net/CAPITAL/OS_YEARS*100:+.2f}%/y")
    one_burst = (top5_sum * 0.5 + rest_net)
    print(f"假设性 P3(爆发频率减半: 2.7 年仅 1 波): 净 ≈ {one_burst:+.0f} USD "
          f"-> 年化 {one_burst/CAPITAL/OS_YEARS*100:+.2f}%/y")
    return dict(clear_notional=cn)


# --------------------------------------------------------------------------- C
def section_c(m: pd.Series) -> None:
    banner("C. 与 A3/B3 月度相关(副引擎分散化证据;干净月度对齐,period 索引)")
    for tag in ("A3", "B3"):
        s = pd.read_csv(ROOT / f"user_data/logs/mtm_daily_{tag}.csv",
                        parse_dates=[0], index_col=0).iloc[:, 0]
        sm = s.resample("ME").last().pct_change()
        sm.index = sm.index.tz_localize(None).to_period("M")
        j = pd.concat([m.rename("grid"), sm.rename(tag)], axis=1, sort=True).dropna()
        r = j.grid.corr(j[tag])
        rs = j.grid.corr(j[tag], method="spearman")
        n = len(j)
        z, se = np.arctanh(r), 1 / np.sqrt(n - 3)
        lo, hi = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
        t = r * np.sqrt(n - 2) / np.sqrt(1 - r ** 2)
        print(f"{tag}: n={n} months  pearson={r:+.3f} (spearman {rs:+.3f})  t={t:+.2f}  "
              f"95%CI [{lo:+.3f}, {hi:+.3f}]")
        if tag == "A3":
            worst8 = j.nsmallest(8, "A3")
            print(f"  A3 最差 8 个月里网格同月合计 {worst8.grid.sum():+.0f} USD")
            worst12 = j.nsmallest(12, "A3")
            print(f"  A3 最差 12 个月里网格同月合计 {worst12.grid.sum():+.0f} USD")
            best6 = j.nlargest(6, "A3")
            print(f"  A3 最好 6 个月里网格同月合计 {best6.grid.sum():+.0f} USD")
            print(f"  (冻结 xcheck 口径: n=17, corr=+0.101 —— MonthEnd(0) 保留时刻导致碎片对齐,本表为修正口径)")


# --------------------------------------------------------------------------- D
def section_d() -> None:
    banner("D. 容量半定量:IS 崩盘窗口 5m bar 名义 vs 10x 资金(本地 5m feather 仅到 2023-12,用 IS 期)")
    eis = pd.read_csv(CHOP_LOGS / "grid_episodes_IS.csv", parse_dates=["t_start", "t_end"])
    wis = eis[(eis.gate == "g2") & (eis["L"] == 12) & (eis.k == 0.5)
              & (eis["mode"] == "dual") & (eis["fill"] == "cross")].copy()
    wis["pnl"] = wis.end_equity - wis.start_equity
    ev = {}
    for pair in ("BTC", "ETH", "SOL"):
        f = pd.read_feather(ROOT / f"user_data/data/binance/futures/{pair}_USDT_USDT-5m-futures.feather")
        f["notional"] = f.volume * f.close
        f["date"] = f["date"].dt.tz_convert("UTC").dt.tz_localize(None)
        ev[pair] = f.set_index("date")["notional"]
    focus = pd.concat([wis.nsmallest(4, "clear_pnl"), wis.nlargest(2, "grid_profit")])
    print(f"IS 选中配置: {len(wis)} eps, net {wis.pnl.sum():+.0f}; 焦点段(最大清仓亏损 4 + 最大毛利 2):")
    lvl_now = 2 * INIT_EQ / L  # per-level notional at 10k/币
    print(f"当前每层名义 ≈ 2×10k/12 = {lvl_now:.0f} USD/层/币; 10x 资金 → {lvl_now*10:.0f} USD/层/币")
    print(f"{'pair':<5}{'t_end':<21}{'clear_pnl':>10}{'max_expo':>10}"
          f"{'bar名义中位(M)':>14}{'bar名义p05(M)':>14}{'10x清仓/bar中位':>15}")
    for _, r in focus.iterrows():
        w = ev[r.pair].loc[r.t_end - pd.Timedelta(hours=2): r.t_end + pd.Timedelta(hours=1)]
        med, p05 = w.median() / 1e6, w.quantile(0.05) / 1e6
        ratio10 = r.max_net_expo * 10 / w.median()
        print(f"{r.pair:<5}{str(r.t_end):<21}{r.clear_pnl:>10.0f}{r.max_net_expo:>10.0f}"
              f"{med:>14.2f}{p05:>14.2f}{ratio10:>15.1%}")
    # 常态(非崩盘)g2 段的 bar 名义中位
    print("\n所有 IS g2 段窗口内 5m bar 名义中位(M USD):")
    for pair in ("BTC", "ETH", "SOL"):
        sub = wis[wis.pair == pair]
        meds = [ev[pair].loc[r.t_start: r.t_end].median() / 1e6 for _, r in sub.iterrows()]
        print(f"  {pair}: median-of-medians {np.median(meds):.2f} M, "
              f"worst-episode median {np.min(meds):.2f} M")


def main() -> None:
    win = load_os()
    a = section_a(win)
    section_b(win, a["tot"])
    section_c(a["m"])
    section_d()
    banner("done")


if __name__ == "__main__":
    main()
