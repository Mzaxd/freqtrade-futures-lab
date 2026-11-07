#!/usr/bin/env python3
"""Sleeve-combo re-verification with OPT9 as sleeve A (item 2, 2026-11-01).

Method (disclosed approximation, applied identically to every sleeve so the
A1-vs-A2 comparison is internally consistent):
  - monthly sleeve returns from trade lists: equity compounds on the sleeve's
    own closed trades (close_date order, 10k start); r_m = sum(pnl in month m)
    / equity at month start
  - portfolio monthly return = sum(w_s * r_s,m); compounded portfolio curve;
    maxDD on the monthly curve; Calmar = CAGR(36m) / maxDD
  - pairwise correlations of monthly return series
This mirrors the phase-7 "monthly closed-trade aggregation" spirit; absolute
numbers are approximations, the A1/OPT4-vs-A2/OPT9 deltas are the deliverable.

Usage: opt9_combo.py  (stdlib only)
"""
import json
import math
import sys
import zipfile

START = 10_000.0


def load(zippath):
    with zipfile.ZipFile(zippath) as z:
        n = [x for x in z.namelist() if x.endswith(".json") and "_config" not in x][0]
        d = json.loads(z.read(n))
    s = next(iter(d["strategy"].values()))
    return s, sorted(s["trades"], key=lambda t: t["close_date"])


def monthly_returns(trades, months):
    """{month: return} with equity compounding on the sleeve's own trades."""
    eq = START
    pnl = {m: 0.0 for m in months}
    for t in trades:
        m = t["close_date"][:7]
        if m in pnl:
            pnl[m] += t["profit_abs"]
    out = {}
    for i, m in enumerate(months):
        out[m] = pnl[m] / eq
        eq += pnl[m]
    return out


def curve(rets):
    eq, peak, maxdd, curve_eq = START, START, 0.0, []
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        maxdd = max(maxdd, 1 - eq / peak)
        curve_eq.append(eq)
    return eq, maxdd


def corr(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (vx * vy) if vx and vy else 0.0


def main():
    months = [f"{y}-{m:02d}" for y in (2021, 2022, 2023) for m in range(1, 13)]
    sleeves = {}
    for name, path in [
        ("A1=OPT4", "user_data/backtest_results/opt9_base_is.zip"),
        ("A2=OPT9", "user_data/backtest_results/opt9_full_is.zip"),
        ("B=MomReg", "user_data/backtest_results/sleeveB_is.zip"),
        ("N=NFI-Lite", "user_data/backtest_results/nfilite_is.zip"),
    ]:
        s, tr = load(path)
        sleeves[name] = monthly_returns(tr, months)
        rets = [sleeves[name][m] for m in months]
        eq, dd = curve(rets)
        cagr = (eq / START) ** (12 / len(months)) - 1
        print(f"{name:<12} trades={s['total_trades']:<4} total={eq/START*100-100:+9.1f}%  "
              f"maxDD(m)={dd*100:5.2f}%  Calmar={cagr/dd if dd else 0:6.2f}")

    def series(name):
        return [sleeves[name][m] for m in months]

    print("\ncorr (monthly):")
    names = list(sleeves)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            print(f"  {a} x {b}: {corr(series(a), series(b)):.3f}")

    def combo(weights):
        rets = []
        for m in months:
            rets.append(sum(w * sleeves[s][m] for s, w in weights.items()))
        eq, dd = curve(rets)
        cagr = (eq / START) ** (12 / len(months)) - 1
        return eq / START * 100 - 100, dd * 100, (cagr / dd if dd else 0)

    print("\ncombos:")
    for a in ("A1=OPT4", "A2=OPT9"):
        tot, dd, cal = combo({a: 1.0})
        print(f"  {a} alone          : {tot:+9.1f}%  DD {dd:5.2f}%  Calmar {cal:6.2f}")
        tot, dd, cal = combo({a: 0.5, "B=MomReg": 0.5})
        print(f"  {a}+B 50/50        : {tot:+9.1f}%  DD {dd:5.2f}%  Calmar {cal:6.2f}")
        tot, dd, cal = combo({a: 0.4, "B=MomReg": 0.4, "N=NFI-Lite": 0.2})
        print(f"  {a}+B+N 40/40/20   : {tot:+9.1f}%  DD {dd:5.2f}%  Calmar {cal:6.2f}")


if __name__ == "__main__":
    sys.exit(main())
