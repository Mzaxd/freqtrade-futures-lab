# WS1 matrix: per-C feasibility checks using measured distributions + live exchange limits.
# Inputs: research_ab/results/ws1_{a_trades,b_orders,b_trades}_dist.csv (from ws1_analyze.py)
# Live constraints fetched 2026-11-03 via ccxt direct (no proxy):
#   BTC minNotional 50, step 0.001, minQty 0.001 | ETH 20/0.001/0.001 | SOL 5/0.01/0.01
#   last: BTC 76767.2, ETH 2261.36, SOL 92.14
import io
import json
import zipfile

import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"

PX = {"BTC": 76767.2, "ETH": 2261.36, "SOL": 92.14}
LIM = {"BTC": dict(minn=50.0, step=0.001), "ETH": dict(minn=20.0, step=0.001),
       "SOL": dict(minn=5.0, step=0.01)}
W_A, W_B = 0.64, 0.36
SL_RES_A = 1.05 / (1 - 0.30)   # A stoploss -0.30 -> 1.5
SL_RES_B = 1.05 / (1 - 0.10)   # B default stoploss -0.10 -> 1.1667
AMOUNT_RES = 1.05
LEVELS = [500, 1000, 1500, 2000, 3000, 5000, 10000]
RECYCLE = [1.0, 1.28, 1.56]


def pairk(p):
    return p.split("/")[0]


def eff_min_notional(sym, sleeve):
    """freqtrade effective min notional (order cost) incl. reserves, sleeve stoploss."""
    res = SL_RES_A if sleeve == "A" else SL_RES_B
    return max(LIM[sym]["minn"] * res, LIM[sym]["step"] * PX[sym] * AMOUNT_RES)


def load_a():
    df = pd.read_csv(ROOT + r"\research_ab\results\ws1_a_trades_dist.csv")
    # corrected sizing stop: from final stop_loss_abs (ATR-anchored; re-read from zip)
    zf = zipfile.ZipFile(ROOT + r"\user_data\backtest_results\backtest-result-2026-11-03_08-22-30.zip")
    main = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n][0]
    d = json.loads(zf.read(main))
    s = list(d["strategy"].values())[0]
    stop = {t["open_date"]: abs(t["open_rate"] - t["stop_loss_abs"]) / t["open_rate"]
            for t in s["trades"]}
    df["stop_pct"] = df["open_date"].map(stop)
    df["nf_implied"] = np.minimum(0.01 / df["stop_pct"], 0.70)  # intended notional frac
    df["sym"] = df["pair"].map(pairk)
    return df


def concurrent_margin_a(dfa):
    """exact hourly sum(open stakes)/equity for sleeve A (base run)."""
    wname = zipfile.ZipFile(
        ROOT + r"\user_data\backtest_results\backtest-result-2026-11-03_08-22-30.zip")
    wf = [n for n in wname.namelist() if n.endswith("wallet.feather")][0]
    w = pd.read_feather(io.BytesIO(wname.read(wf)))
    w = w[w["currency"] == "USDT"][["date", "total_quote"]].sort_values("date")
    w["date"] = pd.to_datetime(w["date"], utc=True)
    tr = dfa.copy()
    tr["open_ts"] = pd.to_datetime(tr["open_date"])
    cl = {}
    zf = zipfile.ZipFile(ROOT + r"\user_data\backtest_results\backtest-result-2026-11-03_08-22-30.zip")
    main = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n][0]
    d = json.loads(zf.read(main))
    s = list(d["strategy"].values())[0]
    for t in s["trades"]:
        cl[t["open_date"]] = pd.Timestamp(t["close_date"])
    tr["close_ts"] = tr["open_date"].map(cl)
    grid = pd.date_range(tr["open_ts"].min(), tr["close_ts"].max(), freq="1h")
    used = np.zeros(len(grid))
    for _, r in tr.iterrows():
        m = (grid >= r["open_ts"]) & (grid < r["close_ts"])
        used[m] += r["stake"]
    eq = pd.Series(
        [float(w["total_quote"].iloc[w["date"].searchsorted(g, side="right") - 1]) for g in grid],
        index=grid)
    return used / eq


def main():
    pd.set_option("display.width", 250)
    dfa = load_a()
    bs = pd.read_csv(ROOT + r"\research_ab\results\ws1_b_orders_dist.csv")
    tb = pd.read_csv(ROOT + r"\research_ab\results\ws1_b_trades_dist.csv")
    bs["sym"] = bs["pair"].map(pairk)
    tb["sym"] = tb["pair"].map(pairk)

    print("### A: corrected sizing stop_pct (final stop_loss_abs) ###")
    print(dfa.groupby("sym")["stop_pct"].describe(
        percentiles=[.05, .25, .5, .75, .95])[["min", "5%", "50%", "95%", "max"]].round(4))
    print("\n### A: intended notional frac = min(0.01/stop, 0.70) ###")
    print(dfa.groupby("sym")["nf_implied"].describe(
        percentiles=[.05, .5, .95])[["min", "5%", "50%", "95%", "max"]].round(4))

    # --- fee quantification, C=1000 ---
    print("\n### fees at C=1000 (taker 0.05% x2 sides) ###")
    for sym, frac in [("BTC", dfa[dfa.sym == "BTC"]["nf_implied"].median()),
                      ("ETH", dfa[dfa.sym == "ETH"]["nf_implied"].median()),
                      ("SOL", dfa[dfa.sym == "SOL"]["nf_implied"].median())]:
        n = frac * W_A * 1000
        print(f"  A {sym}: p50 notional {n:7.1f} USDT -> round-trip fee {n*0.001:6.3f} USDT "
              f"({n*0.001/(0.01*W_A*1000):.1%} of the 6.4 USDT risk budget)")

    # --- B funding conditional on duration >= 18d ---
    long_b = tb[tb["dur"] >= 18]
    short_b = tb[tb["dur"] < 18]
    print("\n### B funding_fees / trade entry notional ###")
    print(f"  all trades      : n={len(tb):3d} median {tb['fund_pct_cost'].median():+.4%} "
          f"mean {tb['fund_pct_cost'].mean():+.4%}")
    print(f"  duration >= 18d : n={len(long_b):3d} median {long_b['fund_pct_cost'].median():+.4%} "
          f"mean {long_b['fund_pct_cost'].mean():+.4%} "
          f"p95 {long_b['fund_pct_cost'].quantile(.95):+.4%}")
    print(f"  duration < 18d  : n={len(short_b):3d} median {short_b['fund_pct_cost'].median():+.4%}")
    # 18d funding if held at +0.01%/8h typical positive funding
    print(f"  reference: +0.01%/8h for 18d = {0.0001*3*18:+.3%} of notional (long pays when positive)")

    # --- concurrency (scale-invariant) ---
    util = concurrent_margin_a(dfa)
    print("\n### A concurrent margin utilization (sum stakes / A equity), scale-invariant ###")
    for k in RECYCLE:
        u = util * k
        print(f"  recycle {k}: max {u.max():.3f}, p99 {u.quantile(.99):.3f}, "
              f"hours >100%: {(u > 1).mean():.3%}, >70%: {(u > .7).mean():.3%}")
    # vs TOTAL account C during bear (B flat): demand = util*W_A*k*C / C
    for k in [1.28, 1.56]:
        d = util * W_A * k
        print(f"  recycle {k} vs TOTAL account: max {d.max():.3f} C, hours >100% C: {(d > 1).mean():.4%}")

    # --- effective min notional floors ---
    print("\n### effective min-notional floors (incl. freqtrade reserves), at live prices ###")
    for sym in ["BTC", "ETH", "SOL"]:
        print(f"  {sym}: exchange floor {LIM[sym]['minn']:.0f} -> A eff {eff_min_notional(sym,'A'):.1f} "
              f"| B eff {eff_min_notional(sym,'B'):.1f} USDT notional")

    # --- C matrix ---
    nf_min = dfa.groupby("sym")["nf_implied"].min()
    nf_p50 = dfa.groupby("sym")["nf_implied"].median()
    nf_p95 = dfa.groupby("sym")["nf_implied"].quantile(.95)
    init_frac = bs[bs["first"]].groupby("sym")["frac_eq"].min()  # ~0.2448
    adds = bs[~bs["first"]]
    rows = []
    for C in LEVELS:
        CA, CB = W_A * C, W_B * C
        r = {"C": C}
        for sym in ["BTC", "ETH", "SOL"]:
            # A: worst-case (smallest) intended notional at this C
            a_min = nf_min[sym] * CA
            a_p50 = nf_p50[sym] * CA
            floor_a = eff_min_notional(sym, "A")
            r[f"A {sym} min>floor"] = a_min >= floor_a
            r[f"A {sym} bump%"] = round(100 * max(0, (floor_a - a_min) / a_min), 1)
            # A BTC granularity: worst-case truncation loss = step*price / notional
            if sym == "BTC":
                r["A BTC p50 step err%"] = round(100 * LIM["BTC"]["step"] * PX["BTC"] / a_p50, 2)
                r["A BTC min step err%"] = round(100 * LIM["BTC"]["step"] * PX["BTC"] / max(a_min, 1e-9), 2)
            # B initial
            b_init = init_frac[sym] * CB
            floor_b = eff_min_notional(sym, "B")
            r[f"B {sym} init>floor"] = b_init >= floor_b
        # B adds skipped at this C
        addc = adds["cost"] * (CB / adds["eq_at"])  # rescale to this C
        fl = adds["sym"].map(lambda s: eff_min_notional(s, "B"))
        r["B adds skipped%"] = round(100 * (addc < fl).mean(), 1)
        r["B add notional skipped%"] = round(100 * addc[addc < fl].sum() / addc.sum(), 1)
        rows.append(r)
    m = pd.DataFrame(rows).set_index("C")
    print("\n### C-level matrix ###")
    print(m.to_string())

    # threshold solve
    print("\n### exact thresholds ###")
    for sym in ["BTC", "ETH", "SOL"]:
        fa, fb = eff_min_notional(sym, "A"), eff_min_notional(sym, "B")
        print(f"  {sym}: A worst trade notional=frac*C_A >= {fa:.1f} -> C >= {fa/nf_min[sym]/W_A:7.1f}"
              f" | B initial >= {fb:.1f} -> C >= {fb/init_frac[sym]/W_B:7.1f}")
    # BTC step 10% bar: notional >= 10*step*price
    bar = 10 * LIM["BTC"]["step"] * PX["BTC"]
    print(f"  BTC step<10% bar: notional >= {bar:.0f} -> at p50 frac: C >= {bar/nf_p50['BTC']/W_A:.0f};"
          f" at min frac: C >= {bar/nf_min['BTC']/W_A:.0f}")
    bar5 = 5 * LIM["BTC"]["step"] * PX["BTC"]
    print(f"  BTC step<20% bar (half convention <10%): notional >= {bar5:.0f} -> "
          f"p50: C >= {bar5/nf_p50['BTC']/W_A:.0f}; min: C >= {bar5/nf_min['BTC']/W_A:.0f}")
    return m


if __name__ == "__main__":
    main()
