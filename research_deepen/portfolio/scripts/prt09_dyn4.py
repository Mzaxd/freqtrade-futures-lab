"""PRT09: dynamic-weight sensitivity + 4th-sleeve (SuperDD) marginal contribution.

A. Monthly inverse-volatility weights (trailing 63d daily MTM vol, >=30d history,
   weights capped [0.1,0.6] then renormalized; first month uses equal weights)
   vs static candidates.  Question: is vol-parity really better or noise?
B. 4-sleeve grid (A,B,N,S on 5% lattice, exact sum 100): best achievable + fixed
   "add S at 10/15/20% replacing others pro-rata" points vs 3-sleeve.

Output: results/dyn4_results.csv + console.
"""
import os
import itertools
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, r"research_deepen\portfolio\results")


def metrics(ret):
    eq = np.cumprod(1 + ret)
    yrs = len(ret) / 365.0
    cagr = eq[-1] ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(365)
    peak = np.maximum.accumulate(eq)
    dd = (eq / peak - 1).min()
    return dict(cagr=cagr, annvol=vol, sharpe=ret.mean() * 365 / vol, maxdd=dd,
                calmar=cagr / abs(dd))


def inverse_vol_weights(daily, cols, window=63, minhist=30, cap=(0.10, 0.60)):
    R = daily[cols].to_numpy(float)
    n, k = R.shape
    wts = np.full((n, k), 1 / k)
    dates = daily.index
    month_starts = np.where(np.r_[True, dates.to_period("M")[1:] != dates.to_period("M")[:-1]])[0]
    for mi in range(len(month_starts) - 1):
        s = month_starts[mi]
        hist_end = s  # use data strictly before month start
        if hist_end < minhist:
            continue
        v = R[max(0, hist_end - window):hist_end].std(axis=0)
        if np.any(~np.isfinite(v)) or np.any(v <= 0):
            continue
        w = 1 / v
        w = w / w.sum()
        w = np.clip(w, *cap)
        w = w / w.sum()
        wts[s:month_starts[mi + 1]] = w
    return wts


def main():
    daily = pd.read_csv(os.path.join(RES, "returns_mtm_daily.csv"), index_col=0, parse_dates=True)
    rows = []

    # --- A. dynamic vs static (3 sleeves) ---
    cols3 = ["A", "B", "N"]
    R3 = daily[cols3].to_numpy(float)
    wts = inverse_vol_weights(daily, cols3)
    rp_dyn = (wts * R3).sum(axis=1)
    m = metrics(rp_dyn)
    rows.append(dict(exp="dyn3_mtm", cand="monthly inverse-vol (63d)", **{k2: round(v, 4) for k2, v in m.items()}))
    for name, w in [("static 40/40/20", [.4, .4, .2]), ("static equal", [1/3]*3)]:
        m = metrics(R3 @ np.array(w))
        rows.append(dict(exp="dyn3_mtm", cand=name, **{k2: round(v, 4) for k2, v in m.items()}))
    # average realized weights of the dynamic scheme
    avgw = wts.mean(axis=0)
    rows.append(dict(exp="dyn3_mtm", cand="dyn avg weights A/B/N",
                     cagr=round(float(avgw[0]), 3), annvol=round(float(avgw[1]), 3),
                     sharpe=round(float(avgw[2]), 3), maxdd=np.nan, calmar=np.nan))

    # --- B. 4-sleeve grid ---
    cols4 = ["A", "B", "N", "S"]
    R4 = daily[cols4].to_numpy(float)
    grid = []
    for a, b, n, s in itertools.product(range(15, 56, 5), range(15, 56, 5), range(10, 36, 5), range(5, 26, 5)):
        if a + b + n + s == 100:
            grid.append((a, b, n, s))
    best, bestm = None, None
    cal_mar = []
    for g in grid:
        m = metrics(R4 @ (np.array(g) / 100))
        cal_mar.append(m["calmar"])
        if bestm is None or m["calmar"] > bestm["calmar"]:
            best, bestm = g, m
    rows.append(dict(exp="grid4_mtm", cand=f"grid max {'/'.join(map(str,best))}", **{k2: round(v, 4) for k2, v in bestm.items()}))
    cal_mar = np.array(cal_mar)
    n95 = int((cal_mar >= cal_mar.max() * 0.95).sum())
    rows.append(dict(exp="grid4_mtm", cand=f"plateau95 count={n95}/{len(grid)}",
                     cagr=round(float(np.median([g[0] for g, c in zip(grid, cal_mar) if c >= cal_mar.max() * .95])), 3),
                     annvol=round(float(np.median([g[1] for g, c in zip(grid, cal_mar) if c >= cal_mar.max() * .95])), 3),
                     sharpe=round(float(np.median([g[2] for g, c in zip(grid, cal_mar) if c >= cal_mar.max() * .95])), 3),
                     maxdd=np.nan, calmar=round(float(cal_mar.max()), 3)))

    # fixed: pro-rata carve-out of S from 40/40/20 and from 45/25/30
    for base_name, base in [("40/40/20", (40, 40, 20)), ("45/25/30", (45, 25, 30))]:
        for s in (10, 15, 20):
            w = np.array([b * (100 - s) / 100 for b in base] + [s]) / 100
            m = metrics(R4 @ w)
            rows.append(dict(exp="grid4_mtm", cand=f"{base_name} +S{s} pro-rata", **{k2: round(v, 4) for k2, v in m.items()}))
    # 3-sleeve references on the same MTM data
    for name, w in [("3sl best 40/20/40", (0.4, 0.2, 0.4, 0.0)), ("3sl 40/40/20", (0.4, 0.4, 0.2, 0.0))]:
        m = metrics(R4 @ np.array(w))
        rows.append(dict(exp="grid4_mtm", cand=name, **{k2: round(v, 4) for k2, v in m.items()}))

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "dyn4_results.csv"), index=False)
    print(df.to_string())


if __name__ == "__main__":
    main()
