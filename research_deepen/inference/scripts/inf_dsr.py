"""inf_dsr.py — Deflated Sharpe Ratio (Bailey & López de Prado 2014) for the
frozen OPT4_VolatilitySystem.

DSR answers: "given that we tried N configurations and picked the best, what is
the probability that the champion's true Sharpe > 0, after deflating for the
selection bias and for non-normality of returns?"

Inputs:
  * frozen OPT4 daily returns (realized-equity basis, 2021-2023) — the
    candidate's own track record;
  * variance of Sharpes across the 75-cell CSCV grid (same window, same data,
    same structure) — the effective dispersion of the search;
  * N = number of trials. Primary N = 75 (fully documented grid). Sensitivity
    to documented historical VolSys-family trial counts from the phase
    reports: phase1 67 + phase2 150 + phase4-paramtune 477 + phase4-structure
    ~15 + phase4-merge 3 = ~712 historical, plus the 75 grid = 787.

Formula (daily, non-annualized SR):
  SR0 = sqrt(V[SR]) * ((1-gamma)*Z(1-1/N) + gamma*Z(1-1/(N e))),  gamma=0.5772
  DSR = Phi( (SR - SR0) sqrt(T-1) / sqrt(1 - g3 SR + (g4-1)/4 SR^2) )
with g3 = skewness, g4 = kurtosis (normal = 3) of daily returns.

Output: research_deepen/inference/results/dsr_results.json
"""
from __future__ import annotations

import glob
import json
import math
import os
import zipfile

import numpy as np
import pandas as pd
from scipy import stats

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RES = os.path.join(REPO, "research_deepen", "inference", "results")
GRID_DIR = os.path.join(RES, "grid")

GAMMA = 0.5772156649015329  # Euler-Mascheroni

N_GRID = 75
HIST_TRIALS = {  # documented VolSys-family search effort (phase reports)
    "phase1_opt1_hyperopt_epochs": 67,
    "phase2_opt2_volsys_epochs": 150,
    "phase4_paramtune_epochs": 477,
    "phase4_structure_variants": 15,
    "phase4_merge_candidates": 3,
}


def daily_sharpe_from_grid_zip(path: str) -> float:
    with zipfile.ZipFile(path) as z:
        jname = [
            n
            for n in z.namelist()
            if n.endswith(".json") and "config" not in n and "market" not in n
        ][0]
        data = json.loads(z.read(jname))
        st = next(iter(data["strategy"].values()))
    # rebuild from trades on the realized-equity daily basis
    t = pd.DataFrame(st["trades"])
    t["close_date"] = pd.to_datetime(t["close_date"], utc=True)
    t = t[t["close_date"].dt.normalize() <= pd.Timestamp("2023-12-31", tz="UTC")]
    t = t.sort_values("close_date")
    eq = 10000.0 + t.set_index("close_date")["profit_abs"].cumsum()
    daily = eq.groupby(eq.index.normalize()).last()
    daily[pd.Timestamp("2021-01-01", tz="UTC")] = 10000.0
    daily = daily.sort_index()
    full = pd.date_range("2021-01-01", "2023-12-31", freq="D", tz="UTC")
    daily = daily.reindex(full).ffill()
    r = daily.pct_change().dropna().to_numpy()
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def sr0(n_trials: int, var_sr: float) -> float:
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(var_sr) * ((1.0 - GAMMA) * z1 + GAMMA * z2)


def dsr(sr: float, t_obs: int, skew: float, kurt: float, sr_star: float) -> float:
    num = (sr - sr_star) * math.sqrt(t_obs - 1)
    den = math.sqrt(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr)
    return float(stats.norm.cdf(num / den))


def main() -> None:
    # frozen OPT4 daily returns
    df = pd.read_csv(
        os.path.join(RES, "daily", "inf_opt4_daily.csv"), index_col=0, parse_dates=True
    )
    r = df["ret"].to_numpy()
    T = len(r)
    sr_daily = float(r.mean() / r.std(ddof=1))
    sr_ann = sr_daily * math.sqrt(252)
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))  # normal = 3

    # variance of Sharpes across the 75 grid cells (same daily basis)
    zips = sorted(glob.glob(os.path.join(GRID_DIR, "s*.zip")))
    assert len(zips) == N_GRID, f"expected 75 grid zips, found {len(zips)}"
    grid_srs = np.array([daily_sharpe_from_grid_zip(z) for z in zips])
    var_sr = float(grid_srs.var(ddof=1))

    hist_total = sum(HIST_TRIALS.values())
    n_curve = [50, 75, 125, 250, 477, hist_total, hist_total + N_GRID]
    rows = []
    for n in n_curve:
        s0 = sr0(n, var_sr)
        d = dsr(sr_daily, T, skew, kurt, s0)
        rows.append({"N_trials": n, "SR0_daily": s0, "DSR": d})
        print(f"N={n:4d}  SR0={s0:.6f} (daily)  DSR={d:.4f}")

    psr_zero = dsr(sr_daily, T, skew, kurt, 0.0)  # Prob SR>0 without selection bias
    out = {
        "sr_daily": sr_daily,
        "sr_annualized": sr_ann,
        "T_days": T,
        "skew": skew,
        "kurtosis": kurt,
        "grid_sharpe_daily_mean": float(grid_srs.mean()),
        "grid_sharpe_daily_std": float(grid_srs.std(ddof=1)),
        "grid_sharpe_daily_min": float(grid_srs.min()),
        "grid_sharpe_daily_max": float(grid_srs.max()),
        "var_sr_across_grid": var_sr,
        "PSR_vs_zero": psr_zero,
        "historical_trial_count_breakdown": HIST_TRIALS,
        "dsr_curve": rows,
        "primary": {"N_trials": 75, "DSR": rows[1]["DSR"]},
    }
    path = os.path.join(RES, "dsr_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(
        f"\nfrozen OPT4: daily SR={sr_daily:.5f} (ann {sr_ann:.3f}), skew={skew:.2f}, "
        f"kurt={kurt:.1f}, T={T}"
    )
    print(f"grid daily SR: mean={grid_srs.mean():.5f} std={grid_srs.std(ddof=1):.5f} "
          f"min={grid_srs.min():.5f} max={grid_srs.max():.5f}")
    print(f"PSR (no selection adjustment) = {psr_zero:.4f}")
    print(f"saved -> {path}")


if __name__ == "__main__":
    main()
