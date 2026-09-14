"""inf_bootstrap.py — stationary-block bootstrap + Monte Carlo on daily returns.

For each stream (inf_opt4, inf_opt2b, inf_nfilite, combo404020):

1. Stationary bootstrap (Politis & Romano 1994) on the daily return series,
   mean block length 10 trading days (geometrically distributed), 10,000 paths.
   Preserves short-range dependence (regime clustering, the realized-PnL
   autocorrelation of multi-day holds) within blocks while allowing arbitrary
   re-combinations — answers: "given the empirical daily-return process, how
   unlucky could the PATH be?" (maxDD / underwater distribution).

2. i.i.d. control: resample daily returns with block length 1 (same paths).
   Difference vs (1) = the contribution of return clustering/autocorrelation
   to tail drawdowns.

3. Trade-level i.i.d. shuffle control: permute the ORDER of per-trade account
   impacts (profit_abs / realized equity at trade close time), rebuild the
   compounding equity. Destroys ALL calendar structure (regime dependence,
   concurrent-slot interaction, clustering) while keeping the marginal
   distribution of per-trade impacts — answers: "is the observed maxDD driven
   by unfavorable SEQUENCING of an otherwise stable edge, or by the tail of
   the per-trade distribution itself?"

Outputs: research_deepen/inference/results/bootstrap_results.json + printed tables.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RES = os.path.join(REPO, "research_deepen", "inference", "results")

N_PATHS = 10_000
MEAN_BLOCK = 10.0
DD_RED_LINE = 0.20
SEED = 42

STREAMS = ["inf_opt4", "inf_opt2b", "inf_nfilite", "combo404020"]


def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap index vector into series of length n."""
    p = 1.0 / mean_block
    idx = np.empty(n, dtype=np.int64)
    idx[0] = rng.integers(n)
    u = rng.random(n)
    for t in range(1, n):
        if u[t] > p:
            j = idx[t - 1] + 1
            idx[t] = 0 if j >= n else j
        else:
            idx[t] = rng.integers(n)
    return idx


def drawdown_metrics(rets: np.ndarray) -> tuple[float, float, float, float]:
    """Return (maxDD, underwater_fraction, max_underwater_days, terminal_return).

    underwater_fraction: share of days strictly below the running peak.
    max_underwater_days: longest consecutive run below the running peak (days).
    """
    eq = np.cumprod(1.0 + rets)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    maxdd = float(dd.min())
    below = eq < peak  # first day eq==peak(=1) so it never counts
    frac = float(below.mean())
    # longest True run
    max_run = run = 0
    for b in below:
        run = run + 1 if b else 0
        max_run = max(max_run, run)
    return maxdd, frac, float(max_run), float(eq[-1] - 1.0)


def run_bootstraps(rets: np.ndarray, rng: np.random.Generator) -> dict:
    n = len(rets)
    out = {}
    for kind in ("stationary_b10", "iid_daily"):
        block = MEAN_BLOCK if kind.startswith("stationary") else 1.0
        dd = np.empty(N_PATHS)
        uw_frac = np.empty(N_PATHS)
        uw_days = np.empty(N_PATHS)
        term = np.empty(N_PATHS)
        for i in range(N_PATHS):
            idx = stationary_bootstrap_indices(n, block, rng)
            dd[i], uw_frac[i], uw_days[i], term[i] = drawdown_metrics(rets[idx])
        out[kind] = summarize(dd, uw_frac, uw_days, term)
    return out


def summarize(dd: np.ndarray, uw_frac: np.ndarray, uw_days: np.ndarray, term: np.ndarray) -> dict:
    """dd comes in as negative ratios; we report DEPTH = -dd (positive %)."""
    depth = -dd
    q = lambda a, p: float(np.quantile(a, p))  # noqa: E731
    return {
        "maxdd_p50": q(depth, 0.50),
        "maxdd_p75": q(depth, 0.75),
        "maxdd_p90": q(depth, 0.90),
        "maxdd_p95": q(depth, 0.95),
        "maxdd_p99": q(depth, 0.99),
        "maxdd_worst": float(depth.max()),
        "p_maxdd_gt_20pct": float((depth > DD_RED_LINE).mean()),
        "p_maxdd_gt_30pct": float((depth > 0.30).mean()),
        "p_maxdd_gt_25pct": float((depth > 0.25).mean()),
        "uw_frac_p50": q(uw_frac, 0.50),
        "uw_frac_p90": q(uw_frac, 0.90),
        "uw_frac_p95": q(uw_frac, 0.95),
        "uw_days_p50": q(uw_days, 0.50),
        "uw_days_p90": q(uw_days, 0.90),
        "uw_days_p95": q(uw_days, 0.95),
        "uw_days_p99": q(uw_days, 0.99),
        "terminal_ret_p5": q(term, 0.05),
        "terminal_ret_p50": q(term, 0.50),
        "terminal_ret_p95": q(term, 0.95),
    }


def trade_shuffle(label: str, rng: np.random.Generator, n_rep: int = 10_000) -> dict:
    """I.i.d. permutation of per-trade account impacts, compounded.

    impact_i = profit_abs_i / realized_equity_at_close_of_previous_trades is
    approximated by profit_abs_i / (running cumsum equity at the close just
    before trade i, chronological). Compounding (1 + impact_perm) rebuilds a
    synthetic equity path of length n_trades.
    """
    trades = pd.read_csv(os.path.join(RES, "trades", f"{label}_trades.csv"))
    t = trades.copy()
    t["close_date"] = pd.to_datetime(t["close_date"], utc=True)
    t = t.sort_values("close_date").reset_index(drop=True)
    eq_prior = 10000.0 + t["profit_abs"].shift(1).fillna(0.0).cumsum()
    impact = (t["profit_abs"] / eq_prior).to_numpy()
    dd = np.empty(n_rep)
    uw = np.empty(n_rep)
    uwd = np.empty(n_rep)
    for i in range(n_rep):
        perm = rng.permutation(impact)
        dd[i], uw[i], uwd[i], _ = drawdown_metrics(perm)
    s = summarize(dd, uw, uwd, np.zeros(n_rep))
    s["n_trades"] = int(len(t))
    s.pop("terminal_ret_p5", None)
    s.pop("terminal_ret_p50", None)
    s.pop("terminal_ret_p95", None)
    s["note"] = "per-trade units (drawdowns compound across trades, not days)"
    return s


def main() -> None:
    results: dict[str, dict] = {}
    for label in STREAMS:
        df = pd.read_csv(os.path.join(RES, "daily", f"{label}_daily.csv"), index_col=0, parse_dates=True)
        rets = df["ret"].to_numpy()
        obs = drawdown_metrics(rets)
        rng = np.random.default_rng(SEED)
        res = {
            "n_days": int(len(rets)),
            "observed": {
                "maxdd": obs[0],
                "uw_frac": obs[1],
                "uw_days_max": obs[2],
                "terminal_ret": obs[3],
            },
            **run_bootstraps(rets, rng),
        }
        if label != "combo404020":
            res["trade_shuffle"] = trade_shuffle(label, np.random.default_rng(SEED))
        results[label] = res
        print(f"done {label}")

    out_path = os.path.join(RES, "bootstrap_results.json")
    Path(out_path).write_text(json.dumps(results, indent=2))

    # ---- printed tables ------------------------------------------------
    def fmt_row(name, d):
        return (
            f"{name:16s} DD p50 {d['maxdd_p50'] * 100:6.1f}%  p90 {d['maxdd_p90'] * 100:6.1f}%  "
            f"p95 {d['maxdd_p95'] * 100:6.1f}%  p99 {d['maxdd_p99'] * 100:6.1f}%  "
            f"worst {d['maxdd_worst'] * 100:6.1f}%  P(DD>20%) {d['p_maxdd_gt_20pct'] * 100:5.1f}%  "
            f"P(DD>30%) {d['p_maxdd_gt_30pct'] * 100:5.1f}%  "
            f"UWfrac p95 {d['uw_frac_p95'] * 100:5.1f}%  UWdays p95 {d['uw_days_p95']:5.0f}"
        )

    for label in STREAMS:
        r = results[label]
        print(f"\n=== {label} (obs maxDD {r['observed']['maxdd'] * 100:.2f}%, "
              f"obs UWfrac {r['observed']['uw_frac'] * 100:.1f}%, "
              f"obs max UW {r['observed']['uw_days_max']:.0f}d) ===")
        print(fmt_row("stationary b=10", r["stationary_b10"]))
        print(fmt_row("iid daily", r["iid_daily"]))
        if "trade_shuffle" in r:
            ts = r["trade_shuffle"]
            print(
                f"{'trade shuffle':16s} DD p50 {ts['maxdd_p50'] * 100:6.1f}%  p90 {ts['maxdd_p90'] * 100:6.1f}%  "
                f"p95 {ts['maxdd_p95'] * 100:6.1f}%  p99 {ts['maxdd_p99'] * 100:6.1f}%  "
                f"worst {ts['maxdd_worst'] * 100:6.1f}%  P(DD>20%) {ts['p_maxdd_gt_20pct'] * 100:5.1f}%  "
                f"P(DD>30%) {ts['p_maxdd_gt_30pct'] * 100:5.1f}%  "
                f"UWtrades p95 {ts['uw_days_p95']:5.0f}"
            )
    print(f"\nsaved -> {out_path}")


if __name__ == "__main__":
    main()
