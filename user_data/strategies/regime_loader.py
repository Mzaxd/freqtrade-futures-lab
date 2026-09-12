"""Shared helpers: load the exported causal regime series and gate signals.

Regime CSVs are produced by regime_detector.py export (causal: mom_z uses only
trailing windows; the turbulent overlay uses trailing percentile ranks).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REGIME_DIR = Path(os.environ.get("FTLAB_REGIME_DIR",
                                 str(Path(__file__).resolve().parent.parent / "regimes")))

STATE_UP, STATE_DOWN, STATE_RANGE, STATE_TURB = 0, 1, 2, 3


def attach_regime(dataframe: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Merge the causal regime series onto an OHLCV frame (backward asof on date).

    The regime value at candle t was computed from data up to t's close; signals
    formed on candle t execute at t+1 open (freqtrade semantics) - no lookahead.
    """
    csv = REGIME_DIR / f"{pair.replace('/', '_').replace(':', '_')}_regime.csv"
    reg = pd.read_csv(csv, parse_dates=["date"])
    reg = reg.dropna().sort_values("date")
    reg["date"] = reg["date"].astype(dataframe["date"].dtype)  # align precision for merge_asof
    out = pd.merge_asof(dataframe.sort_values("date"), reg, on="date", direction="backward")
    if "regime" not in out.columns:
        out["regime"] = -1
        out["conf"] = 0.0
    return out


def risk_scale_for_regime(state: int, conf: float, base_risk: float) -> float:
    """Confidence-scaled risk budget. Turbulent -> 0 (pause); low conf -> reduced."""
    if state == STATE_TURB:
        return 0.0
    return base_risk * max(min(conf, 1.0), 0.0)
