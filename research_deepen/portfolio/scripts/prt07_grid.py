"""PRT07: static weight grid scan for the 3-sleeve portfolio (A/B/N), both conventions.

Grid: A in {20..60 step5}, B in {20..60 step5}, N = 100-A-B must be in {10..40}
(exact-sum lattice, no renormalization drift).  Daily rebalanced fixed weights:
r_p(t) = sum_i w_i * r_i(t).  Metrics: CAGR (365d), ann vol, Sharpe, maxDD, Calmar.

Outputs: results/grid_scan.csv, console heatmaps, plateau definition:
  plateau = combos with Calmar >= (grid_max - 2) i.e. within 2 Calmar points of the max
  (and, separately, >=95% of max).  Also single points: 40/40/20, equal, 50/50 A/B,
  A only, B only, N only.
"""
import os
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, r"research_deepen\portfolio\results")


def metrics(ret: np.ndarray, days_per_year=365.0):
    eq = np.cumprod(1 + ret)
    yrs = len(ret) / days_per_year
    total = eq[-1] - 1
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(days_per_year)
    sharpe = ret.mean() * days_per_year / vol if vol > 0 else np.nan
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak - 1).min()
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    return total, cagr, vol, sharpe, dd, calmar


def scan(daily: pd.DataFrame):
    cols = ["A", "B", "N"]
    R = daily[cols].to_numpy(float)
    combos = []
    for a in range(20, 61, 5):
        for b in range(20, 61, 5):
            n = 100 - a - b
            if 10 <= n <= 40:
                combos.append((a / 100, b / 100, n / 100))
    rows = []
    for a, b, n in combos:
        rp = R @ np.array([a, b, n])
        t, c, v, s, dd, ca = metrics(rp)
        rows.append(dict(A=a, B=b, N=n, total=round(t, 4), cagr=round(c, 4),
                         annvol=round(v, 4), sharpe=round(s, 3),
                         maxdd=round(dd, 4), calmar=round(ca, 3)))
    df = pd.DataFrame(rows)
    # named points
    named = {}
    for name, w in [("40/40/20", (0.4, 0.4, 0.2)), ("equal", (1 / 3, 1 / 3, 1 / 3)),
                    ("50/50 AB", (0.5, 0.5, 0.0)), ("A only", (1.0, 0, 0)),
                    ("B only", (0, 1.0, 0)), ("N only", (0, 0, 1.0)),
                    ("50/30/20", (0.5, 0.3, 0.2)), ("30/50/20", (0.3, 0.5, 0.2)),
                    ("35/35/30", (0.35, 0.35, 0.30)), ("45/35/20", (0.45, 0.35, 0.2)),
                    ("35/45/20", (0.35, 0.45, 0.2))]:
        rp = R @ np.array(w)
        named[name] = tuple(round(x, 4) for x in metrics(rp))
    return df, named


def heat(df, val, title):
    print(f"\n== {title}: {val} (rows=A%, cols=B%, N=100-A-B) ==")
    p = df.pivot(index="A", columns="B", values=val)
    p.index = [f"{int(x*100)}" for x in p.index]
    p.columns = [f"{int(x*100)}" for x in p.columns]
    print(p.to_string(float_format=lambda x: f"{x:6.2f}" if abs(x) < 100 else f"{x:6.1f}"))


def main():
    out = {}
    for conv, fn in [("realized", "returns_daily.csv"), ("mtm", "returns_mtm_daily.csv")]:
        daily = pd.read_csv(os.path.join(RES, fn), index_col=0, parse_dates=True)
        df, named = scan(daily)
        df.to_csv(os.path.join(RES, f"grid_scan_{conv}.csv"), index=False)
        out[conv] = (df, named)
        print(f"\n########## {conv} ##########")
        best = df.loc[df["calmar"].idxmax()]
        print("grid max Calmar:", best.to_dict())
        for thr, tag in [(2.0, "within2"), (0.05, "pct95")]:
            if tag == "within2":
                sel = df[df["calmar"] >= df["calmar"].max() - thr]
            else:
                sel = df[df["calmar"] >= df["calmar"].max() * (1 - thr)]
            print(f"plateau[{tag}]: n={len(sel)} A med={sel['A'].median():.3f} "
                  f"B med={sel['B'].median():.3f} N med={sel['N'].median():.3f} "
                  f"calmar min/med/max={sel['calmar'].min():.2f}/{sel['calmar'].median():.2f}/{sel['calmar'].max():.2f} "
                  f"maxdd range=[{sel['maxdd'].min():.3f},{sel['maxdd'].max():.3f}]")
        print("named points (total, cagr, annvol, sharpe, maxdd, calmar):")
        for k, v in named.items():
            print(f"  {k:10s} {v}")
        heat(df, "calmar", f"{conv}")
        heat(df, "maxdd", f"{conv}")
        heat(df, "cagr", f"{conv}")


if __name__ == "__main__":
    main()
