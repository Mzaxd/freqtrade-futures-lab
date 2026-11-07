"""LVG line 1 — A-sleece volatility-targeted risk_pct (2026-11-07).

Hypothesis (research_improve/lvg/pre_reg.md): the 2023/24 benchmark gap is an
AMPLITUDE problem, not an edge problem. A's notional = equity * risk_pct /
stop_pct has no leverage term, so risk_pct is the only true exposure dial.
Overlay: risk_eff = risk_pct * m_t, m_t = clamp(T / RV30_t, lo, hi), with
RV30_t = annualized stdev of the last 30 log returns of FULLY CLOSED BTC
daily candles (days D-30..D-1 when now is inside day D — strictly causal,
the spec's 1-day shift).

Implementation: override OPT9_VolatilitySystem._risk_fraction (the hook
OPT9 added exactly for sizing overlays). It multiplies the risk in
custom_stake_amount BEFORE OPT9_Recycle applies RECYCLE_MULT — the baseline
ARL_2x stack (recycle 1.21, lev 2) is inherited unchanged; this file only
adds the m_t factor.

Data access mirrors OPT9_Recycle._recycle_on: dp.get_pair_dataframe(BTC 1h)
raw frame (cut at the current candle by freqtrade), self-sliced strictly
before current_time, resampled to 1D with the incomplete trailing day
dropped, warmup (<31 closed days) -> m = 1.0 (neutral, no amplification).
Cache keyed on (len(df), idx) like the recycle cache.

Pre-registered cells (see pre_reg.md; IS 21-23 median RV30 = 60.6):
  LVG_A_vt60   T=60.6 clamp [0.5, 2.0]   (spec default)
  LVG_A_vt60f1 T=60.6 clamp [1.0, 2.0]   (never de-risk below base)
  LVG_A_vt50   T=50.6 clamp [0.5, 1.5]   (conservative)
  LVG_A_r2     constant m=2.0            (= risk_pct 0.02 amplitude anchor)
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from AB_LevGrid import ARL_2x


class LVG_A_VolTarget(ARL_2x):
    # --- vol-target knobs (pre-registered) ---
    VT_TARGET = 60.6      # T, annualized % (IS 21-23 median RV30)
    VT_M_LO = 0.5
    VT_M_HI = 2.0

    # per-candle cache: (len(df), idx) -> m
    _vt_cache: tuple | None = None

    # ------------------------------------------------------------------ RV30
    def _rv30_pct(self, current_time: datetime) -> float | None:
        """Annualized stdev (%) of the last 30 log returns of fully-closed
        BTC daily candles, from data strictly before current_time.
        None when fewer than 31 closed days are available (warmup)."""
        if self.dp is None:
            return None
        df = self.dp.get_pair_dataframe(self.RECYCLE_REF, self.timeframe)
        if df is None or len(df) == 0:
            return None
        ts = pd.Timestamp(current_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        idx = int(df["date"].searchsorted(ts.floor("ms"))) - 1
        if idx < 24 * 35:   # < 35 days of 1h data -> surely < 31 closed days
            return None
        key = (len(df), idx)
        if self._vt_cache is not None and self._vt_cache[0] == key:
            return self._vt_cache[1]
        closes = df["close"].iloc[: idx + 1]
        closes.index = pd.DatetimeIndex(df["date"].iloc[: idx + 1])
        daily = closes.resample("1D").last()
        # drop trailing incomplete day: bin [D, D+1) closed iff ts >= D+1
        while len(daily) and (daily.index[-1] + pd.Timedelta(days=1)) > ts:
            daily = daily.iloc[:-1]
        rv = None
        if len(daily) >= 31:
            rets = (daily / daily.shift(1)).dropna()
            rets = rets.iloc[-30:]
            rets = rets[rets > 0]
            if len(rets) == 30:
                lr = rets.map(lambda x: math.log(x))
                mu = sum(lr) / 30.0
                var = sum((x - mu) ** 2 for x in lr) / 29.0   # ddof=1
                rv = math.sqrt(var) * math.sqrt(365.0) * 100.0
        self._vt_cache = (key, rv)
        return rv

    # ------------------------------------------------------------------ dial
    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        rv = self._rv30_pct(current_time)
        if rv is None or rv <= 0:
            return 1.0
        m = float(self.VT_TARGET) / rv
        return min(max(m, float(self.VT_M_LO)), float(self.VT_M_HI))


class LVG_A_vt60(LVG_A_VolTarget):
    VT_TARGET = 60.6
    VT_M_LO = 0.5
    VT_M_HI = 2.0


class LVG_A_vt60f1(LVG_A_VolTarget):
    VT_TARGET = 60.6
    VT_M_LO = 1.0
    VT_M_HI = 2.0


class LVG_A_vt50(LVG_A_VolTarget):
    VT_TARGET = 50.6
    VT_M_LO = 0.5
    VT_M_HI = 1.5


class LVG_A_r2(ARL_2x):
    """Constant amplitude anchor: risk x2 (== risk_pct 0.02, the known
    'returns and drawdowns scale equally' reference point)."""
    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        return 2.0
