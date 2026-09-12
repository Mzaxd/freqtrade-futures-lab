"""opt_common.py — Phase-1 optimization shared helpers (research/backtest grade).

Public API:
    attach_funding(dataframe, pair)  -> adds causal `funding_rate` column
    funding_gate_long(df, threshold) -> bool Series, True = long entry ALLOWED

Semantics (anti-lookahead):
  * Funding feathers hold one row per 8h funding settlement (date, funding_rate).
  * We shift the event series by ONE settlement (8h) before merging as-of the
    candle timestamps: a candle at time t can only see the rate settled at the
    event *before* the latest one <= t.  The newest settled rate is only final
    at its own settlement instant, so this keeps the gate strictly causal.
  * Pairs without funding data (e.g. LINK/DOT/LTC/UNI in this lab) get NaN ->
    the gate treats NaN as "no information -> do not block", and the fact is
    logged once per pair so reports can disclose it.

Live/dry-run caveat: this module reads the lab's feather files directly.  It is
intended for backtest research; a live deployment would need to swap
`_funding_events` for an exchange API fetch.  Documented deliberately.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

FUNDING_FEATHER_DIR = Path(__file__).resolve().parents[2] / "data" / "binance" / "futures"

_missing_pairs: set[str] = set()


@lru_cache(maxsize=64)
def _funding_events(pair: str) -> Optional[pd.Series]:
    """Settled funding rates for `pair`, index=UTC settlement time. None if absent."""
    base = pair.split("/")[0]
    f = FUNDING_FEATHER_DIR / f"{base}_USDT_USDT-1h-funding_rate.feather"
    if not f.exists():
        if pair not in _missing_pairs:
            _missing_pairs.add(pair)
            logger.warning("opt_common: no funding feather for %s (%s) — gate off", pair, f.name)
        return None
    s = pd.read_feather(f)
    s["date"] = pd.to_datetime(s["date"], utc=True)
    return s.set_index("date")["funding_rate"].sort_index()


def attach_funding(dataframe: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Add a causal `funding_rate` column (rate of the settlement BEFORE the
    latest one as of each candle) to a strategy dataframe.  No-op (NaN column)
    when funding data is missing for the pair."""
    dataframe = dataframe.copy()
    dataframe["funding_rate"] = float("nan")
    events = _funding_events(pair)
    if events is None or events.empty:
        return dataframe
    causal = events.shift(1).dropna()          # only fully-settled prior rates
    left = dataframe[["date"]].copy()
    left["date"] = pd.to_datetime(left["date"], utc=True)
    right = causal.rename("funding_rate").reset_index()  # col 'date' kept
    # pandas 3 merge_asof demands identical datetime resolutions on both keys
    left["date"] = left["date"].astype("datetime64[us, UTC]")
    right["date"] = right["date"].astype("datetime64[us, UTC]")
    merged = pd.merge_asof(
        left.sort_values("date"),
        right,
        on="date",
        direction="backward",
    )
    dataframe["funding_rate"] = merged["funding_rate"].to_numpy()
    return dataframe


def funding_gate_long(dataframe: pd.DataFrame, threshold: float) -> pd.Series:
    """True where opening a LONG is allowed: latest settled funding rate must be
    <= threshold (NaN/missing -> allowed).  threshold is per-8h rate, e.g.
    0.0005 = 0.05%/8h; a large sentinel (e.g. 1.0) effectively disables the gate
    and keeps the parameter inside a smooth hyperopt space."""
    fr = dataframe["funding_rate"]
    return (fr.isna()) | (fr <= threshold)


def funding_gate_short(dataframe: pd.DataFrame, threshold: float) -> pd.Series:
    """Mirror of funding_gate_long for shorts: block when settled funding is
    very negative (shorts pay).  Phase-1 spec only requires the long gate; this
    exists so symmetric variants don't reinvent it."""
    fr = dataframe["funding_rate"]
    return (fr.isna()) | (fr >= -abs(threshold))
