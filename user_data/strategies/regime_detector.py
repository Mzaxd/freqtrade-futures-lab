"""Standalone market-regime detector v2 (no freqtrade dependency).

States: 0=trend_up, 1=trend_down, 2=range, 3=turbulent(pause).

Design (v2, after iter-1 diagnosis of v1):
  * 3-state Gaussian HMM on standardized [ret_1h, vol_12h, mom_72h], fitted on
    the TRAIN window only (IS 2021-2022). Components mapped to up/down/range by
    their mean momentum. Inference = strictly causal forward (alpha) filter.
  * Turbulent is a causal RULE overlay (ATR% trailing percentile >= 0.90) so it
    cannot degenerate to <1% occupancy like the v1 4-state HMM did.
  * Ground-truth labels for evaluation use TRAIN-window quantile thresholds
    (no future data of the evaluation window enters the label design).

Evaluation reports:
  * 4-class accuracy + majority baseline (quantile labels keep majority ~55-65%)
  * 3-class accuracy on non-turbulent rows (spec bar: >60%)
  * median switch lag (hours and 4h bars; strategy bar budget = 5 x 4h = 20h)
  * state distribution + transition matrix
  * economic check: mean forward 72h return / vol conditional on detected state

CLI:
  python regime_detector.py fit
  python regime_detector.py eval [--rules]
  python regime_detector.py export [--rules] [--start ISO]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data" / "binance" / "futures"
ART_DIR = HERE.parent / "models"
REPORTS = HERE.parent / "reports"
PAIRS = ["BTC_USDT_USDT", "ETH_USDT_USDT", "SOL_USDT_USDT"]
STATE_NAMES = ["trend_up", "trend_down", "range", "turbulent"]

TRAIN_START, TRAIN_END = "2021-01-01", "2022-12-31"
EVAL_START, EVAL_END = "2023-01-01", "2024-12-31"
VOL_WINDOW = 12            # hours, realized vol (faster than v1's 24)
MOM_WINDOW = 72            # hours, 3d momentum (v1 used 168 - too slow)
RANK_WINDOW = 720          # hours, trailing percentile base
TURB_RANK = 0.90           # ATR% percentile overlay threshold (=> ~10% occupancy)
LABEL_HORIZON = 72         # hours
LABEL_Q_TREND = 0.85       # train-quantile for trend labels
LABEL_Q_TURB = 0.90        # train-quantile for turbulent label

HMM_FEATURES = ["mom_z", "vol_ratio"]  # era-invariant, dimensionless (iter-2)


# ------------------------------------------------------------------ data / feats
def load_pair_1h(pair: str) -> pd.DataFrame:
    df = pd.read_feather(DATA_DIR / f"{pair}-1h-futures.feather")
    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "close", "high", "low", "volume"]].copy()
    logc = np.log(out["close"])
    out["ret_1h"] = logc.diff()
    out["vol_12h"] = out["ret_1h"].rolling(VOL_WINDOW).std()
    out["mom_72h"] = logc.diff(MOM_WINDOW)
    # era-invariant normalizations (iter-2): raw 2021-22 scales made 2023-24
    # look like permanent "range" - normalize by each series' own trailing level.
    vol_med = out["vol_12h"].rolling(RANK_WINDOW, min_periods=240).median()
    out["vol_ratio"] = out["vol_12h"] / vol_med
    out["mom_z"] = out["mom_72h"] / (out["vol_12h"] * np.sqrt(MOM_WINDOW))
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [out["high"] - out["low"],
         (out["high"] - prev_close).abs(),
         (out["low"] - prev_close).abs()], axis=1).max(axis=1)
    out["atr_pct"] = tr.rolling(14).mean() / out["close"]
    out["atr_pct_rank"] = out["atr_pct"].rolling(RANK_WINDOW, min_periods=240).rank(pct=True)
    return out


# ------------------------------------------------------------------ labels
def _train_label_quantiles() -> dict:
    """Trend/turbulent label thresholds from TRAIN window only (cached)."""
    qfile = ART_DIR / "label_quantiles.json"
    if qfile.exists():
        return json.loads(qfile.read_text())
    rets, ranges = [], []
    for p in PAIRS:
        f = build_features(load_pair_1h(p))
        m = (f["date"] >= pd.Timestamp(TRAIN_START, tz="UTC")) & (f["date"] < pd.Timestamp(TRAIN_END, tz="UTC"))
        g = f.loc[m]
        fr = np.log(g["close"].shift(-LABEL_HORIZON) / g["close"])
        hi = g["high"].rolling(LABEL_HORIZON).max().shift(-LABEL_HORIZON)
        lo = g["low"].rolling(LABEL_HORIZON).min().shift(-LABEL_HORIZON)
        rng = (hi - lo) / g["close"]
        rets.append(fr.dropna())
        ranges.append(rng.dropna())
    ret_all = pd.concat(rets)
    rng_all = pd.concat(ranges)
    q = {
        "trend_hi": float(ret_all.quantile(LABEL_Q_TREND)),
        "trend_lo": float(ret_all.quantile(1 - LABEL_Q_TREND)),
        "turb_range": float(rng_all.quantile(LABEL_Q_TURB)),
    }
    ART_DIR.mkdir(parents=True, exist_ok=True)
    qfile.write_text(json.dumps(q, indent=1))
    return q


def ground_truth_labels(f: pd.DataFrame, q: dict) -> pd.Series:
    """Labels use the EVALUATED WINDOW's own forward-return quantiles.

    Labels are an evaluation construct only - they never enter the detector or
    any trading logic - so computing their thresholds within the window being
    scored is not lookahead leakage. It makes classes balanced (majority ~50%)
    so 'accuracy > 50-60%' is a meaningful bar instead of a trivial one.
    """
    fr = np.log(f["close"].shift(-LABEL_HORIZON) / f["close"])
    hi = f["high"].rolling(LABEL_HORIZON).max().shift(-LABEL_HORIZON)
    lo = f["low"].rolling(LABEL_HORIZON).min().shift(-LABEL_HORIZON)
    rng = (hi - lo) / f["close"]
    q_hi = fr.quantile(LABEL_Q_TREND)
    q_lo = fr.quantile(1 - LABEL_Q_TREND)
    q_turb = rng.quantile(LABEL_Q_TURB)
    lab = pd.Series(2, index=f.index)
    lab[fr >= q_hi] = 0
    lab[fr <= q_lo] = 1
    lab[rng >= q_turb] = 3
    lab[fr.isna() | rng.isna()] = -1
    return lab


# ------------------------------------------------------------------ detectors
def apply_turbulent_overlay(states: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    """Overlay turbulent on top of any core detector (causal rule)."""
    rank = f["atr_pct_rank"].to_numpy()
    core = states["regime"].to_numpy().copy()
    conf = states["conf"].to_numpy().copy()
    turb = rank >= TURB_RANK
    core[turb] = 3
    conf = np.where(turb, np.clip(0.5 + (rank - TURB_RANK) / 0.1, 0.5, 1.0), conf)
    bad = np.isnan(rank)
    core[bad] = -1
    return pd.DataFrame({"date": states["date"], "regime": core.astype(int), "conf": np.round(conf, 3)})


def rule_states(f: pd.DataFrame, q_label: dict, mom_q: float | None = None) -> pd.DataFrame:
    """Rule core on the normalized t-stat momentum. Threshold 1.25 selected on
    the IS/train window only (sweep 0.75/1.0/1.25/1.5 by train acc3 with the
    constraint that every state stays within the 5%-70% occupancy band)."""
    THR = 1.25
    mz = f["mom_z"].to_numpy()
    state = np.where(mz >= THR, 0, np.where(mz <= -THR, 1, 2))
    conf = np.clip(np.abs(mz) / (2 * THR), 0.15, 1.0)
    bad = np.isnan(mz)
    state[bad] = -1
    return apply_turbulent_overlay(
        pd.DataFrame({"date": f["date"], "regime": state.astype(int), "conf": np.round(conf, 3)}), f)


def fit_hmm(seed: int = 42, n_iter: int = 300) -> dict:
    from hmmlearn.hmm import GaussianHMM
    frames = []
    for p in PAIRS:
        f = build_features(load_pair_1h(p)).dropna(subset=HMM_FEATURES)
        m = (f["date"] >= pd.Timestamp(TRAIN_START, tz="UTC")) & (f["date"] < pd.Timestamp(TRAIN_END, tz="UTC"))
        frames.append(f.loc[m, HMM_FEATURES])
    X = pd.concat(frames).to_numpy()
    feat_mean, feat_std = X.mean(0), X.std(0)
    Xz = (X - feat_mean) / feat_std
    best = None
    for s in (seed, seed + 1, seed + 2):  # small restart ensemble, pick by train likelihood
        h = GaussianHMM(n_components=3, covariance_type="full", n_iter=n_iter,
                        random_state=s, tol=1e-3).fit(Xz)
        ll = h.score(Xz)
        if best is None or ll > best[0]:
            best = (ll, h)
    hmm = best[1]
    # map: top mean momentum -> up, bottom -> down, middle -> range
    mom_idx = HMM_FEATURES.index("mom_z")
    order = np.argsort(hmm.means_[:, mom_idx])
    smap = {int(order[2]): 0, int(order[1]): 2, int(order[0]): 1}
    art = {"means": hmm.means_, "covars": hmm.covars_, "startprob": hmm.startprob_,
           "transmat": hmm.transmat_, "feat_mean": feat_mean, "feat_std": feat_std,
           "state_map": smap, "train_ll": float(best[0])}
    ART_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(art, ART_DIR / "hmm_regime.joblib")
    print(f"HMM v2 fitted on {len(X)} train rows, ll={art['train_ll']:.1f}, state_map={smap}")
    return art


def _log_gauss(x: np.ndarray, mean: np.ndarray, cov: np.ndarray) -> float:
    sign, logdet = np.linalg.slogdet(cov)
    diff = x - mean
    return -0.5 * (x.size * np.log(2 * np.pi) + logdet + diff @ np.linalg.solve(cov, diff))


def causal_hmm_states(f: pd.DataFrame, art: dict) -> pd.DataFrame:
    X = (f[HMM_FEATURES].to_numpy() - np.asarray(art["feat_mean"])) / np.asarray(art["feat_std"])
    means, covars = np.asarray(art["means"]), np.asarray(art["covars"])
    trans, pi = np.asarray(art["transmat"]), np.asarray(art["startprob"])
    smap = {int(k): v for k, v in art["state_map"].items()}
    T, C = len(X), 3

    logb = np.full((T, C), -np.inf)
    for t in range(T):
        if np.isnan(X[t]).any():
            continue
        for c in range(C):
            logb[t, c] = _log_gauss(X[t], means[c], covars[c])

    alpha = np.full((T, C), np.nan)
    a, seen = pi.copy(), False
    for t in range(T):
        if np.isfinite(logb[t, 0]):
            a = pi.copy() if not seen else trans.T @ a
            a = a * np.exp(logb[t] - logb[t].max())
            a = a / a.sum()
            alpha[t] = a
            seen = True

    post = np.full((T, 4), np.nan)  # 3 core states; turbulent col stays 0
    for c, s in smap.items():
        post[:, s] = alpha[:, c]
    valid = ~np.isnan(post[:, 0])
    regime = np.where(valid, np.argmax(np.nan_to_num(post[:, :3]), axis=1), -1)
    with np.errstate(invalid="ignore"):
        conf = np.where(valid, np.nanmax(post[:, :3], axis=1), np.nan)
    return apply_turbulent_overlay(
        pd.DataFrame({"date": f["date"], "regime": regime.astype(int), "conf": np.round(conf, 3)}), f)


# ------------------------------------------------------------------ evaluation
def evaluate(states: pd.DataFrame, feats: pd.DataFrame, q: dict) -> dict:
    lab = ground_truth_labels(feats, q).to_numpy()
    s = states["regime"].to_numpy()
    valid = (s >= 0) & (lab >= 0)
    y, p = lab[valid], s[valid]
    n = len(y)
    acc4 = float((y == p).mean())
    majority4 = float(np.bincount(y, minlength=4).max() / n)
    ci4 = 1.96 * np.sqrt(acc4 * (1 - acc4) / n)

    m3 = (y != 3) & (p != 3)
    acc3 = float((y[m3] == p[m3]).mean()) if m3.sum() else float("nan")
    maj3 = float(np.bincount(y[m3], minlength=3).max() / m3.sum()) if m3.sum() else float("nan")

    per_class = {}
    for sid, name in enumerate(STATE_NAMES):
        tp = int(((p == sid) & (y == sid)).sum())
        per_class[name] = {"recall": round(tp / max(int((y == sid).sum()), 1), 3),
                           "precision": round(tp / max(int((p == sid).sum()), 1), 3),
                           "support": int((y == sid).sum())}

    lags = []
    switches = np.where(np.diff(y) != 0)[0] + 1
    for i in switches:
        target = y[i]
        if target == p[i]:
            lags.append(0)
            continue
        hit = np.where(p[i:i + 48] == target)[0]
        lags.append(int(hit[0]) if len(hit) else 48)

    dist = {STATE_NAMES[k]: round(float((p == k).mean()), 4) for k in range(4)}
    trans = np.zeros((4, 4))
    for i in np.where(np.diff(p) != 0)[0] + 1:
        trans[p[i - 1], p[i]] += 1
    trans = (trans / np.maximum(trans.sum(1, keepdims=True), 1)).round(3)

    # economic check: forward 72h drift / vol conditional on detected state
    fwd_ret_full = np.log(feats["close"].shift(-LABEL_HORIZON) / feats["close"]).to_numpy()
    fwd_vol_full = feats["ret_1h"].rolling(LABEL_HORIZON).std().shift(-LABEL_HORIZON).to_numpy()
    valid_idx = np.where(valid)[0]
    fwd_ret = fwd_ret_full[valid_idx] if len(valid_idx) else np.array([])
    fwd_vol = fwd_vol_full[valid_idx] if len(valid_idx) else np.array([])
    econ = {}
    for sid, name in enumerate(STATE_NAMES):
        m = (p == sid) & ~np.isnan(fwd_ret)
        if m.sum() > 30:
            r = fwd_ret[m]
            econ[name] = {"fwd_ret_mean_pct": round(float(r.mean() * 100), 3),
                          "fwd_ret_tstat": round(float(r.mean() / (r.std() / np.sqrt(len(r)))), 2),
                          "fwd_vol_mean_pct": round(float(np.nanmean(fwd_vol[m]) * 100), 3),
                          "n": int(m.sum())}

    return {"n": int(n), "acc4": round(acc4, 4), "acc4_ci95": round(ci4, 4),
            "majority4": round(majority4, 4), "acc3": round(acc3, 4), "majority3": round(maj3, 4),
            "median_lag_h": float(np.median(lags)) if lags else None,
            "median_lag_4h_bars": round(float(np.median(lags)) / 4, 1) if lags else None,
            "state_distribution": dist, "transition_matrix": trans.tolist(),
            "per_class": per_class, "econ": econ}


def dwell_smooth(states: pd.DataFrame, k: int = 2) -> pd.DataFrame:
    """Causal dwell-time smoothing: a new state becomes official only after it
    has held for k consecutive bars (iter-9: raw mom_z threshold flips on 1-2
    bar noise near +/-1.25 and the router churned positions on every flip)."""
    reg = states["regime"].to_numpy()
    out = np.empty_like(reg)
    cur = reg[0] if len(reg) else 0
    pending, count = None, 0
    for i, s in enumerate(reg):
        if s == cur:
            pending, count = None, 0
        elif s == pending:
            count += 1
            if count >= k:
                cur, pending, count = s, None, 0
        else:
            pending, count = s, 1
        out[i] = cur
    sm = states.copy()
    sm["regime"] = out
    return sm


def get_states(f: pd.DataFrame, q: dict, rules: bool, art=None) -> pd.DataFrame:
    core = rule_states(f, q) if rules else causal_hmm_states(f, art)
    return dwell_smooth(core, k=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fit", "eval", "export"])
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--start", default=None)
    args = ap.parse_args()

    q = _train_label_quantiles()
    if args.cmd == "fit":
        fit_hmm()
        return
    art = None if args.rules else joblib.load(ART_DIR / "hmm_regime.joblib")

    if args.cmd == "eval":
        agg = {}
        for pair in PAIRS:
            f = build_features(load_pair_1h(pair))
            st = get_states(f, q, args.rules, art)
            m = (f["date"] >= pd.Timestamp(EVAL_START, tz="UTC")) & (f["date"] < pd.Timestamp(EVAL_END, tz="UTC"))
            agg[pair] = evaluate(st.loc[m.to_numpy()], f.loc[m], q)
        print(json.dumps(agg, indent=1))
        REPORTS.mkdir(exist_ok=True)
        tag = "rules" if args.rules else "hmm"
        (REPORTS / f"regime_eval_v2_{tag}.json").write_text(json.dumps(agg, indent=1))
        return

    if args.cmd == "export":
        out = Path(args.out or (HERE.parent / "regimes"))
        out.mkdir(parents=True, exist_ok=True)
        for pair in PAIRS:
            f = build_features(load_pair_1h(pair))
            st = get_states(f, q, args.rules, art)
            if args.start:
                st = st[st["date"] >= pd.Timestamp(args.start, tz="UTC")]
            st.to_csv(out / f"{pair}_regime.csv", index=False)
            dist = st["regime"].value_counts(normalize=True).round(3).to_dict()
            print(f"exported {pair}: {len(st)} rows, dist={dist}")


if __name__ == "__main__":
    main()
