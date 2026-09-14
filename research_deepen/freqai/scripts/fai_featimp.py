#!/usr/bin/env python
"""FAI featimp: aggregate LightGBM feature importances (gain) from FreqAI backtest
model artifacts, plus permutation importance on representative models/years.

Usage: python fai_featimp.py <identifier>
Writes results to stdout. Gain part mirrors S4's OPT7_featimp approach;
permutation part rebuilds features via the strategy code (trees are scale-invariant,
raw features are fine) and measures logloss/AUC degradation per shuffled column.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE / "research_deepen" / "freqai" / "strategies"))
import FAI_V1  # noqa: E402

DATA = BASE / "user_data" / "data" / "binance" / "futures"
MODELS = BASE / "user_data" / "models"


def gain_importance(identifier: str) -> pd.Series:
    files = sorted(glob.glob(str(MODELS / identifier / "sub-train-*" / "*_model.joblib")))
    frames = []
    for mf in files:
        mod = joblib.load(mf)
        fi = getattr(mod, "feature_importances_", None)
        if fi is None:
            continue
        # exact per-model feature order = what survived VarianceThreshold in the
        # saved feature pipeline (some windows drop zero-variance features)
        pipe_files = glob.glob(str(Path(mf).parent / "*feature_pipeline.pkl"))
        names = []
        if pipe_files:
            try:
                names = list(joblib.load(pipe_files[0]).steps[0][1].feature_list)
            except Exception:
                names = []
        if len(names) != len(fi):
            meta = glob.glob(str(Path(mf).parent / "*_metadata.json"))
            names = json.load(open(meta[0]))["training_features_list"] if meta else []
        if len(names) != len(fi):
            names = [f"f{i}" for i in range(len(fi))]
        frames.append(pd.Series(fi, index=names, dtype=float))
    imp = pd.concat(frames, axis=1).mean(axis=1)
    return imp / imp.sum()


def build_labeled(coin: str) -> pd.DataFrame:
    class S:
        pass

    df = pd.read_feather(DATA / f"{coin}_USDT_USDT-1h-futures.feather")
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df = FAI_V1.FAI_V1.feature_engineering_standard(S(), df, {"pair": f"{coin}/USDT:USDT"})
    df = FAI_V1.FAI_V1.set_freqai_targets(S(), df, {})
    return df


def permutation_importance(identifier: str, coins=("BTC", "SOL", "ADA"), year=2023, seed=7):
    """Sample one model per ~quarter trained in `year`, evaluate on that year's rows
    AFTER its train stop (walk-forward honest), permute each feature column."""
    from sklearn.metrics import log_loss, roc_auc_score

    rng = np.random.default_rng(seed)
    rows = []
    for coin in coins:
        df = build_labeled(coin)
        fcols = [c for c in df.columns if c.startswith("%-")]
        subdirs = sorted(glob.glob(str(MODELS / identifier / f"sub-train-{coin}_*")))
        in_year = [sd for sd in subdirs
                   if pd.Timestamp(int(Path(sd).name.split("_")[-1]), unit="s", tz="UTC").year == year]
        picks = in_year[::2]  # every 2nd model trained for `year` predictions
        for sd in picks:
            ts = int(Path(sd).name.split("_")[-1])
            train_stop = pd.Timestamp(ts, unit="s", tz="UTC")
            if train_stop.year < year:  # only models whose predictions fall in `year`
                continue
            lo, hi = train_stop, train_stop + pd.Timedelta(days=35)
            ev = df.loc[(df["date"] >= lo) & (df["date"] < hi)].dropna(subset=fcols + ["&-tb"])
            if len(ev) < 200:
                continue
            mod = joblib.load(glob.glob(str(Path(sd) / "*_model.joblib"))[0])
            # faithful path: transform eval features through the model's own saved
            # feature pipeline (handles VarianceThreshold feature drops + scaling)
            pf = glob.glob(str(Path(sd) / "*_feature_pipeline.pkl"))[0]
            fp = joblib.load(pf)
            classes = list(mod.classes_)
            up_idx = classes.index("up")
            y = (ev["&-tb"] == "up").to_numpy().astype(int)
            if y.min() == y.max():
                continue
            X = fp.transform(ev[fcols].copy())[0]
            X = np.asarray(X, dtype=float)
            keep = getattr(fp.steps[0][1], "feature_list", None)
            pcols = list(keep) if keep is not None and len(keep) == X.shape[1] else list(fcols)

            def score(M):
                p = mod.predict_proba(M)[:, up_idx]
                eps = 1e-6
                p = np.clip(p, eps, 1 - eps)
                return log_loss(y, p), roc_auc_score(y, p)

            base_ll, base_auc = score(X)
            for j, col in enumerate(pcols):
                Xp = X.copy()
                rng.shuffle(Xp[:, j])
                ll, auc = score(Xp)
                rows.append({"coin": coin, "model_ts": str(train_stop.date()), "feature": col,
                             "d_logloss": ll - base_ll, "d_auc": base_auc - auc})
    return pd.DataFrame(rows)


def main(identifier: str):
    print(f"=== GAIN importance (mean over all sub-train models), identifier={identifier} ===")
    gain = gain_importance(identifier)
    for name, v in gain.sort_values(ascending=False).items():
        print(f"{v * 100:6.2f}%  {name}")

    print("\n=== PERMUTATION importance (logloss increase / AUC drop, walk-forward eval) ===")
    perm = permutation_importance(identifier)
    if perm.empty:
        print("(no evaluable models)")
        return
    agg = perm.groupby("feature").agg(d_logloss_mean=("d_logloss", "mean"),
                                      d_auc_mean=("d_auc", "mean"),
                                      n=("d_logloss", "size")).sort_values("d_logloss_mean", ascending=False)
    print(agg.round(5).to_string())
    perm.to_csv(BASE / "research_deepen" / "freqai" / "results" / "fai_perm_raw.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fai_v1")
