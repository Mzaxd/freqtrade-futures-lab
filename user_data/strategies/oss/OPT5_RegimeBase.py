# OPT5_RegimeBase — Phase-5 Door-3 regime overlay base (Agent-K).
#
# Inherits the frozen OPT4_VolatilitySystem and attaches the lab's causal BTC
# regime series (user_data/regimes/BTC_USDT_USDT_regime.csv, 1h, semantics
# 0=trend_up 1=trend_dn 2=range 3=turbulent) onto the 1h strategy frame.
#
# Causal alignment (same convention as user_data/strategies/regime_loader.py
# attach_regime): merge_asof backward on candle date — candle t carries the
# regime computed from data up to t's close; a signal formed on t executes at
# t+1's open under freqtrade semantics, so no lookahead.
#
# Window discipline: the CSV itself extends to 2026-09; it is filtered here to
# date < 2024-01-01 (the phase-5 IS boundary) before merging. Backtests using
# this class must stay inside 20210101-20240101.
#
# This base makes NO trading changes by itself — behavior is identical to
# OPT4 unless a subclass overrides entry gating / sizing.
from pathlib import Path

import pandas as pd
from pandas import DataFrame

from OPT4_VolatilitySystem import OPT4_VolatilitySystem

_REGIME_CUTOFF = pd.Timestamp("2024-01-01", tz="UTC")


class OPT5_RegimeBase(OPT4_VolatilitySystem):
    regime_csv = Path(__file__).resolve().parent.parent.parent / \
        "regimes" / "BTC_USDT_USDT_regime.csv"
    _regime_cache: pd.DataFrame | None = None  # class-level, loaded once

    def _load_regime(self) -> pd.DataFrame:
        if OPT5_RegimeBase._regime_cache is None:
            reg = pd.read_csv(self.regime_csv, parse_dates=["date"])
            reg = reg.dropna().sort_values("date")
            reg = reg[reg["date"] < _REGIME_CUTOFF]  # IS-window filter
            OPT5_RegimeBase._regime_cache = reg
        return OPT5_RegimeBase._regime_cache

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        reg = self._load_regime().copy()
        reg["date"] = reg["date"].astype(dataframe["date"].dtype)
        out = pd.merge_asof(dataframe.sort_values("date"), reg,
                            on="date", direction="backward")
        out["regime"] = out["regime"].fillna(-1).astype(int)
        return out
