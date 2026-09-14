"""PRT08: weight-recommendation uncertainty via stationary bootstrap on daily returns.

For MTM (primary) and realized (reference) daily sleeve returns:
  1. FIXED candidates evaluated on every bootstrap path (10,000 reps, mean block 10d):
     Calmar/maxDD percentile CIs for 40/40/20, equal, 45/30/25, 45/25/30 (pct95-plateau
     median on lattice), 40/20/40 (grid max), A-only.
  2. Per-rep GRID ARGMAX weights -> distribution of the selected vertex itself
     (how unstable is in-sample weight picking).

Output: results/weights_bootstrap.csv + console.
"""
import os
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, r"research_deepen\portfolio\results")
rng = np.random.default_rng(42)
NREP = 10000
MEAN_BLOCK = 10


def stationary_idx(n, nrep, mean_block):
    p = 1.0 / mean_block
    idx = np.empty((nrep, n), dtype=np.int64)
    for r in range(nrep):
        i = 0
        while i < n:
            cur = int(rng.integers(0, n))
            L = int(rng.geometric(p))
            take = min(L, n - i)
            idx[r, i:i + take] = (cur + np.arange(take)) % n
            i += take
    return idx


def calmar_dd(ret):
    eq = np.cumprod(1 + ret, axis=1)
    yrs = ret.shape[1] / 365.0
    cagr = eq[:, -1] ** (1 / yrs) - 1
    peak = np.maximum.accumulate(eq, axis=1)
    dd = (eq / peak - 1).min(axis=1)
    return cagr / np.abs(dd), dd


CANDS = {
    "A40/B40/N20": (0.40, 0.40, 0.20),
    "equal": (1 / 3, 1 / 3, 1 / 3),
    "A45/B30/N25": (0.45, 0.30, 0.25),
    "A45/B25/N30": (0.45, 0.25, 0.30),
    "A40/B20/N40": (0.40, 0.20, 0.40),
    "A only": (1.0, 0.0, 0.0),
}
GRID = [(a, b, (100 - a - b) / 100) for a in range(20, 61, 5) for b in range(20, 61, 5)
        if 10 <= 100 - a - b <= 40]
GRID_W = np.array([[a / 100, b / 100, n] for a, b, n in GRID])


def main():
    rows = []
    for conv, fn in [("mtm", "returns_mtm_daily.csv"), ("realized", "returns_daily.csv")]:
        daily = pd.read_csv(os.path.join(RES, fn), index_col=0, parse_dates=True)[["A", "B", "N"]]
        R = daily.to_numpy(float)
        n = R.shape[0]
        idx = stationary_idx(n, NREP, MEAN_BLOCK)
        paths = R[idx]  # (NREP, n, 3)

        for name, w in CANDS.items():
            rp = paths @ np.array(w)
            ca, dd = calmar_dd(rp)
            rows.append(dict(conv=conv, cand=name,
                             calmar_med=round(np.median(ca), 2),
                             calmar_lo=round(np.percentile(ca, 2.5), 2),
                             calmar_hi=round(np.percentile(ca, 97.5), 2),
                             dd_med=round(np.median(dd), 3),
                             dd_lo=round(np.percentile(dd, 2.5), 3),
                             dd_hi=round(np.percentile(dd, 97.5), 3)))
            print(rows[-1])

        # per-rep grid argmax
        best_w = np.zeros((NREP, 3))
        best_ca = np.full(NREP, -np.inf)
        for w in GRID_W:
            rp = paths @ w
            ca, _ = calmar_dd(rp)
            upd = ca > best_ca
            best_ca[upd] = ca[upd]
            best_w[upd] = w
        for i, nm in enumerate("ABN"):
            q = np.percentile(best_w[:, i], [2.5, 25, 50, 75, 97.5])
            rows.append(dict(conv=conv, cand=f"argmax {nm} weight",
                             calmar_med=round(np.median(best_ca), 2),
                             calmar_lo=round(np.percentile(best_ca, 2.5), 2),
                             calmar_hi=round(np.percentile(best_ca, 97.5), 2),
                             dd_med=round(q[2], 3), dd_lo=round(q[0], 3), dd_hi=round(q[4], 3)))
            print(rows[-1])
        # optimism gap: per-rep argmax calmar minus fixed 40/40/20 calmar on same rep
        rp4040 = paths @ np.array(CANDS["A40/B40/N20"])
        ca4040, _ = calmar_dd(rp4040)
        gap = best_ca - ca4040
        rows.append(dict(conv=conv, cand="argmax-minus-40/40/20 calmar gap",
                         calmar_med=round(np.median(gap), 2),
                         calmar_lo=round(np.percentile(gap, 2.5), 2),
                         calmar_hi=round(np.percentile(gap, 97.5), 2)))
        print(rows[-1])
    pd.DataFrame(rows).to_csv(os.path.join(RES, "weights_bootstrap.csv"), index=False)


if __name__ == "__main__":
    main()
