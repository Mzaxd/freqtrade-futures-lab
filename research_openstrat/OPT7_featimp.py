#!/usr/bin/env python
"""OPT7_featimp.py — Phase 7 S4: aggregate LightGBM feature importances from
FreqAI backtest model artifacts (user_data/models/<identifier>/sub-train-*/*_model.joblib).

Usage: OPT7_featimp.py <identifier> [top_n]
Prints: per-model count, top-N features by mean importance (across sub-trains),
and the aggregate importance share of the OPT7 own features.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import joblib
import pandas as pd

OWN_KEYS = ("funding", "btc4h", "atr_pctl")
BASE = Path(__file__).resolve().parents[1]


def main(identifier: str, top_n: int = 25) -> None:
    model_files = sorted(
        glob.glob(str(BASE / "user_data" / "models" / identifier / "sub-train-*" / "*_model.joblib"))
    )
    if not model_files:
        print(f"no models for identifier {identifier}")
        sys.exit(1)

    frames = []
    for mf in model_files:
        blob = joblib.load(mf)
        model = blob["model"] if isinstance(blob, dict) and "model" in blob else blob
        # freqtrade LightGBMRegressor wraps lgbm; feature names from sibling metadata
        meta = glob.glob(str(Path(mf).parent / "*_metadata.json"))
        names = None
        if meta:
            import json

            with open(meta[0]) as fp:
                names = json.load(fp)["training_features_list"]
        fi = getattr(model, "feature_importances_", None)
        if fi is None and hasattr(model, "model"):
            fi = getattr(model.model, "feature_importances_", None)
        if fi is None:
            print(f"skip {mf}: no feature_importances_ ({type(model)})")
            continue
        # prefer the model's own trained feature names; some sub-trains drop
        # zero-variance features so metadata list length can differ
        names = list(getattr(model, "feature_name_", None) or []) or names
        if names is None or len(names) != len(fi):
            names = [f"f{i}" for i in range(len(fi))]
        frames.append(pd.Series(fi, index=names, dtype=float))

    n_models = len(frames)
    imp = pd.concat(frames, axis=1).mean(axis=1).sort_values(ascending=False)
    total = imp.sum()
    print(f"identifier={identifier} models_aggregated={n_models} features={len(imp)}")
    print(f"total_importance={total:.0f}")
    print("\nTOP %d by mean gain-importance:" % top_n)
    for name, v in imp.head(top_n).items():
        print(f"{v / total * 100:6.2f}%  {name}")
    own = imp[[i for i in imp.index if any(k in i for k in OWN_KEYS)]]
    print("\nOWN FEATURES:")
    if len(own) == 0:
        print("  (none in this arm)")
    for name, v in own.sort_values(ascending=False).items():
        print(f"{v / total * 100:6.2f}%  {name}")
    print(f"own_share_total={own.sum() / total * 100:.2f}%")


if __name__ == "__main__":
    ident = sys.argv[1] if len(sys.argv) > 1 else "opt7_smoke"
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    main(ident, top)
