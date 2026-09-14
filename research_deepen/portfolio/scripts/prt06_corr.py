"""PRT06: pairwise sleeve correlations with stationary/circular block bootstrap CIs.

Point estimates + 95% percentile CIs (10,000 reps) for:
  - monthly returns, realized & MTM conventions (36 obs, circular block bootstrap, block=6 months)
  - daily returns, MTM & realized (1095 obs, Politis-Romano stationary bootstrap, mean block=10d)
Blocks are resampled JOINTLY across sleeves (same time indices) so cross-sleeve
dependence is preserved; uncertainty comes from which time blocks we happen to have.

Output: results/corr_bootstrap.csv + console tables.
"""
import os
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, r"research_deepen\portfolio\results")
rng = np.random.default_rng(20260914)
NREP = 10000


def circular_block_indices(n, block, nrep):
    """Fixed-length circular block bootstrap indices, same for all series."""
    idx = np.empty((nrep, n), dtype=np.int64)
    nb = int(np.ceil(n / block))
    for r in range(nrep):
        starts = rng.integers(0, n, size=nb)
        cols = np.arange(block)[None, :] + starts[:, None]
        idx[r] = (cols % n).ravel()[:n]
    return idx


def stationary_indices(n, mean_block, nrep):
    """Politis-Romano stationary bootstrap indices (geometric blocks, circular).

    Each block gets a FRESH uniform random start on the circle (otherwise the
    sampler degenerates to a permutation, to which correlation is invariant).
    """
    p = 1.0 / mean_block
    idx = np.empty((nrep, n), dtype=np.int64)
    for r in range(nrep):
        out = np.empty(n, dtype=np.int64)
        i = 0
        while i < n:
            cur = int(rng.integers(0, n))
            L = int(rng.geometric(p))
            take = min(L, n - i)
            out[i:i + take] = (cur + np.arange(take)) % n
            i += take
        idx[r] = out
    return idx


def corr_set(df):
    c = df.corr()
    return c


def pairwise_cis(data: np.ndarray, idx: np.ndarray, names):
    """data: (T, k); idx: (R, T). Return dict pair->(lo, med, hi) via batch corr."""
    R, T = idx.shape
    k = data.shape[1]
    out = {}
    # batch: (R, T, k)
    samp = data[idx]  # R x T x k
    samp = samp - samp.mean(axis=1, keepdims=True)
    sd = np.sqrt((samp ** 2).sum(axis=1))  # R x k
    for i in range(k):
        for j in range(i + 1, k):
            num = (samp[:, :, i] * samp[:, :, j]).sum(axis=1)
            r = num / (sd[:, i] * sd[:, j])
            out[(names[i], names[j])] = (np.percentile(r, 2.5), np.percentile(r, 50), np.percentile(r, 97.5))
    return out


def main():
    daily_mtm = pd.read_csv(os.path.join(RES, "returns_mtm_daily.csv"), index_col=0, parse_dates=True)
    daily_rz = pd.read_csv(os.path.join(RES, "returns_daily.csv"), index_col=0, parse_dates=True)
    mon_mtm = pd.read_csv(os.path.join(RES, "returns_mtm_monthly.csv"), index_col=0)
    mon_rz = pd.read_csv(os.path.join(RES, "returns_monthly.csv"), index_col=0)
    names = list(daily_mtm.columns)

    results = []
    for label, df, kind in [
        ("monthly_realized", mon_rz, "block6m"),
        ("monthly_mtm", mon_mtm, "block6m"),
        ("daily_mtm", daily_mtm, "sb10d"),
        ("daily_realized", daily_rz, "sb10d"),
    ]:
        arr = df.to_numpy(float)
        T = arr.shape[0]
        idx = circular_block_indices(T, 6, NREP) if kind == "block6m" else stationary_indices(T, 10, NREP)
        pt = pd.DataFrame(arr, columns=df.columns).corr()
        cis = pairwise_cis(arr, idx, list(df.columns))
        for (a, b), (lo, med, hi) in cis.items():
            results.append(dict(basis=label, pair=f"corr({a},{b})",
                                point=round(pt.loc[a, b], 4),
                                lo95=round(lo, 4), med=round(med, 4), hi95=round(hi, 4)))
    res = pd.DataFrame(results)
    res.to_csv(os.path.join(RES, "corr_bootstrap.csv"), index=False)

    for label in res["basis"].unique():
        sub = res[res["basis"] == label]
        print(f"\n== {label} ==")
        print(sub.to_string(index=False))

    # yearly monthly-return point correlations (descriptive)
    dm = daily_mtm.copy()
    dm["year"] = dm.index.year
    print("\n== yearly point corr, monthly MTM returns ==")
    for y, g in dm.groupby("year"):
        m = (1 + g[names]).groupby(pd.PeriodIndex(g.index, freq="M").astype(str)).prod() - 1
        print(y, "\n", m.corr().round(2).to_string())


if __name__ == "__main__":
    main()
