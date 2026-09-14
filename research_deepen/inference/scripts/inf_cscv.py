"""inf_cscv.py — CSCV / PBO (Bailey & López de Prado) on the 75-config grid.

Input : research_deepen/inference/results/grid/s*_*.zip (75 full-window
        2021-2023 backtests of the OPT4 structure).
Method:
  * daily return matrix M (1095 days x 75 configs), realized-equity basis
    (trade profit_abs cumsum by close date) — identical to the baseline
    streams, and the boundary-forced close at 2024-01-01 excluded.
  * K = 6 half-year blocks; all C(6,3) = 20 train/test partitions.
  * per-config per-period performance = annualized daily Sharpe.
  * PBO: per split, take the top n = N//2 = 37 configs by train Sharpe;
    omega_j = test_rank_j / N for those; lambda = 1 if median(omega) <= 0.5
    (train-chosen configs land in the bottom half out-of-sample);
    PBO = mean(lambda). PBO > 0.5 ~ the selection process is overfit.
  * Rank IC: Spearman correlation between train and test Sharpe ranks
    (all 75 configs) per split — monotone skill transfer, not just tails.
  * Frozen champion (s20_t20_r3) placement tracked per split.

Output: research_deepen/inference/results/cscv_results.json
"""
from __future__ import annotations

import glob
import io
import itertools
import json
import os
import zipfile

import numpy as np
import pandas as pd
from scipy import stats

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GRID_DIR = os.path.join(REPO, "research_deepen", "inference", "results", "grid")
RES = os.path.join(REPO, "research_deepen", "inference", "results")

CUTOFF = pd.Timestamp("2023-12-31", tz="UTC")
START = pd.Timestamp("2021-01-01", tz="UTC")
N_TRIALS_EXPECTED = 75
FROZEN = "s20_t20_r3"


def daily_returns_from_zip(path: str) -> pd.Series:
    with zipfile.ZipFile(path) as z:
        jname = [
            n
            for n in z.namelist()
            if n.endswith(".json") and "config" not in n and "market" not in n
        ][0]
        data = json.loads(z.read(jname))
        name, st = next(iter(data["strategy"].items()))
        trades = pd.DataFrame(st["trades"])
    t = trades.copy()
    t["close_date"] = pd.to_datetime(t["close_date"], utc=True)
    t = t[t["close_date"].dt.normalize() <= CUTOFF].sort_values("close_date")
    eq = 10000.0 + t.set_index("close_date")["profit_abs"].cumsum()
    daily = eq.groupby(eq.index.normalize()).last()
    daily[START] = 10000.0
    daily = daily.sort_index()
    full = pd.date_range(START, CUTOFF, freq="D", tz="UTC")
    daily = daily.reindex(full).ffill()
    ret = daily.pct_change()
    ret.iloc[0] = daily.iloc[0] / 10000.0 - 1.0
    return ret


def ann_sharpe(rets: np.ndarray) -> float:
    sd = rets.std(ddof=1)
    return float(rets.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0


def half_year_blocks() -> list[tuple[str, pd.DatetimeIndex]]:
    blocks = []
    for y in (2021, 2022, 2023):
        for h, (m0, m1) in enumerate([(1, 6), (7, 12)]):
            start = pd.Timestamp(f"{y}-{m0:02d}-01", tz="UTC")
            end = pd.Timestamp(f"{y}-{m1:02d}-01", tz="UTC") + pd.offsets.MonthEnd(1)
            days = pd.date_range(start, end, freq="D", tz="UTC")
            blocks.append((f"{y}H{h + 1}", days))
    return blocks


def main() -> None:
    zips = sorted(glob.glob(os.path.join(GRID_DIR, "s*.zip")))
    tags = [os.path.basename(z)[: -len(".zip")] for z in zips]
    print(f"grid zips found: {len(zips)}")
    assert len(zips) == N_TRIALS_EXPECTED, "expected 75 grid zips"

    M = pd.DataFrame({tag: daily_returns_from_zip(z) for tag, z in zip(tags, zips)})
    M = M[M.index <= CUTOFF]
    print(f"matrix: {M.shape[0]} days x {M.shape[1]} configs, NaNs={int(M.isna().sum().sum())}")

    blocks = half_year_blocks()
    day_to_block = {}
    for bi, (bname, days) in enumerate(blocks):
        for d in days:
            day_to_block[d] = bi

    bidx = np.array([day_to_block.get(d, -1) for d in M.index])
    assert (bidx >= 0).all()

    # per-config per-block Sharpe
    block_sharpe = np.zeros((len(blocks), M.shape[1]))
    for bi in range(len(blocks)):
        mask = bidx == bi
        for ci in range(M.shape[1]):
            block_sharpe[bi, ci] = ann_sharpe(M.to_numpy()[mask, ci])

    N = M.shape[1]
    n_top = N // 2
    results = {"n_configs": N, "n_days": int(M.shape[0]), "blocks": [b[0] for b in blocks],
               "metric": "annualized daily Sharpe", "n_top": n_top, "splits": []}
    lambdas = []
    rank_ics = []
    frozen_train_ranks = []
    frozen_test_ranks = []
    omega_medians = []

    for train_blocks in itertools.combinations(range(6), 3):
        test_blocks = tuple(b for b in range(6) if b not in train_blocks)
        tr_mask = np.isin(bidx, train_blocks)
        te_mask = np.isin(bidx, test_blocks)
        tr_sharpe = np.array([ann_sharpe(M.to_numpy()[tr_mask, ci]) for ci in range(N)])
        te_sharpe = np.array([ann_sharpe(M.to_numpy()[te_mask, ci]) for ci in range(N)])
        tr_rank = stats.rankdata(-tr_sharpe)  # 1 = best
        te_rank = stats.rankdata(-te_sharpe)
        top = np.argsort(tr_sharpe)[::-1][:n_top]
        omega = te_rank[top] / N
        omega_med = float(np.median(omega))
        lam = 1.0 if omega_med <= 0.5 else 0.0
        ic, _ = stats.spearmanr(tr_sharpe, te_sharpe)
        lambdas.append(lam)
        rank_ics.append(float(ic))
        omega_medians.append(omega_med)
        fi = tags.index(FROZEN)
        frozen_train_ranks.append(int(tr_rank[fi]))
        frozen_test_ranks.append(int(te_rank[fi]))
        results["splits"].append({
            "train": [blocks[b][0] for b in train_blocks],
            "test": [blocks[b][0] for b in test_blocks],
            "lambda": lam,
            "median_omega_of_train_top": omega_med,
            "rank_ic": float(ic),
            "frozen_train_rank": int(tr_rank[fi]),
            "frozen_test_rank": int(te_rank[fi]),
        })

    full_sharpe = np.array([ann_sharpe(M.to_numpy()[:, ci]) for ci in range(N)])
    results["summary"] = {
        "PBO": float(np.mean(lambdas)),
        "rank_ic_mean": float(np.mean(rank_ics)),
        "rank_ic_min": float(np.min(rank_ics)),
        "rank_ic_max": float(np.max(rank_ics)),
        "rank_ic_positive_fraction": float(np.mean(np.array(rank_ics) > 0)),
        "omega_median_mean": float(np.mean(omega_medians)),
        "frozen_full_window_sharpe": float(full_sharpe[tags.index(FROZEN)]),
        "frozen_full_window_rank": int(stats.rankdata(-full_sharpe)[tags.index(FROZEN)]),
        "best_full_window": tags[int(np.argmax(full_sharpe))],
        "sharpe_grid_mean": float(full_sharpe.mean()),
        "sharpe_grid_std": float(full_sharpe.std(ddof=1)),
        "sharpe_grid_min": float(full_sharpe.min()),
        "sharpe_grid_max": float(full_sharpe.max()),
    }

    out = os.path.join(RES, "cscv_results.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)

    s = results["summary"]
    print(json.dumps(s, indent=2))
    print(f"\nPBO = {s['PBO']:.3f}  rank IC mean = {s['rank_ic_mean']:.3f} "
          f"[{s['rank_ic_min']:.3f}, {s['rank_ic_max']:.3f}]")
    print(f"frozen s20_t20_r3 full-window Sharpe {s['frozen_full_window_sharpe']:.3f} "
          f"(rank {s['frozen_full_window_rank']}/75); grid best = {s['best_full_window']}")
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
