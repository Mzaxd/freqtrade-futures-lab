"""OPT9_Recycle — dynamic capital-recycle multiplier for sleeve A (2026-11-03, WS3).

Research question (research_ab): in the AB two-sleeve portfolio, sleeve B
(OPT2_MomRegime15mLb21) sits flat whenever BTC's last CLOSED daily close is
below its SMA100 (B's risk_on switch, REGIME_SMA=100, TOLERANCE=0). While B is
off, its capital allocation can be recycled into sleeve A by multiplying A's
per-trade stake. Candidate multipliers (pre-registered, from the static 64/36
allocation): 1.28 (half recycle, A gets 64+18 of 82) and 1.56 (full recycle,
A gets 100 of 64). This file implements that sizing overlay on the OPT9
flagship with entries/exits/stops BYTE-IDENTICAL to OPT9_VolatilitySystem.

Signal definition — matches B's switch exactly (same closed daily bar):
  B (OPT1_MomRegime15mFast._compute_xs) reads FULL-HISTORY daily feathers and
  computes, per daily row D: known = close.shift(1), risk_on[D] =
  known[D] > known.rolling(100).mean()[D], ffilled onto intraday rows of day D.
  Unpacked: during intraday day D, B is on iff close(D-1) > mean(close(D-100..D-1)).
  OPT9_Recycle computes the same quantity from the BTC 1h frame (raw, via
  dp.get_pair_dataframe — see the causality section below): resample closes
  to 1D (UTC day bins, last() per bin), drop the final
  (incomplete) day, then recycle_on = close(last closed day) <= SMA100(last
  100 closed days). On day D the last closed day is D-1, so recycle_on(D) ==
  NOT B.risk_on(D) including the equality edge (TOLERANCE=0: B is on only on a
  STRICT >, so equality means B off -> recycle on). The 1h->1D resample was
  verified against the daily feather over 2020-09-01..2026-09-14: 2203 days,
  max abs close diff = 0.0 (see research_ab/ws3_recycle_impl.md).

Causality mechanics (the d09ba64/OPT8 tz lessons applied):
  * data source: dp.get_pair_dataframe(BTC, 1h) — the raw frame cut at the
    current candle by freqtrade itself (see _recycle_on: get_analyzed_dataframe
    is capped at 1000 candles in backtest and can NEVER feed a daily SMA100);
  * the signal is derived ONLY from candles strictly before current_time
    (searchsorted on the date column, same idiom as OPT8._signal_candle),
    which also drops the just-opened current candle;
  * current_time is normalized to tz-aware UTC and floored to the ms grid
    before searchsorted (lossless unit conversion, no swallowed exceptions);
  * a UTC day bin is used only once it is fully closed: bin [D, D+1) is
    dropped unless current_time >= D+1 (at exactly 00:00 the previous day
    counts as closed — same boundary B uses, since B's daily row D applies
    from 00:00 of day D onward);
  * warmup: with the inherited startup_candle_count=200 (1h), the in-frame
    daily history is too short for SMA100 until ~2021-04-02 in the standard
    20210101- backtest. NaN SMA -> recycle OFF (no amplification). B itself
    was risk_on for every day of that warmup window (verified from the
    feather), so the default coincides with B-synced behavior for the
    standard window; for any OTHER start date the first ~100 days fall back
    to no-amplification (disclosed limitation, matters for deployment: WS4).

Sizing semantics (ONLY new entries; open positions are never resized):
  stake = super().custom_stake_amount(...)   # OPT8 1%-risk sizing, unchanged
  if recycle_on: stake *= RECYCLE_MULT; stake = min(stake, max_stake)
  A multiplier flip therefore cannot touch an in-flight position — the
  recycle overlay only changes the margin committed at entry time. With
  RECYCLE_MULT == 1.0 the method returns super()'s value untouched (the
  signal is not even evaluated): bit-identical regression mode.

RECYCLE_HYSTERESIS_DAYS (default 0 = synchronized with B, no hysteresis):
  0 -> state = raw condition each day (B-sync). H > 0 -> the state flips ON
  (OFF) only after the raw condition has held for H+1 consecutive days
  (first day + H confirmation days), i.e. H=1 is "2-day confirmation".
  Default 0 is the pre-registered point; H is exposed for the WS3 whipsaw
  follow-up only — do NOT grid it silently.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from OPT9_VolatilitySystem import OPT9_VolatilitySystem

logger = logging.getLogger(__name__)


class OPT9_Recycle(OPT9_VolatilitySystem):
    # --- recycle overlay knobs (pre-registered; NOT hyperopt parameters) ---
    RECYCLE_REF = "BTC/USDT:USDT"   # same ref pair as B's REGIME_REF
    RECYCLE_SMA = 100               # == B's REGIME_SMA, daily candles
    RECYCLE_MULT = 1.28             # half recycle (64+18)/64; 1.56 = full
    RECYCLE_HYSTERESIS_DAYS = 0     # 0 = flip exactly when B's switch flips

    # last computed (cache key -> state) — see _recycle_on
    _recycle_state_cache: tuple | None = None

    def informative_pairs(self):
        # guarantee the BTC 1h frame is fed even if BTC is not whitelisted
        # (live/dry-run; in this lab's universes BTC always is).
        pairs = super().informative_pairs()
        wl = self.dp.current_whitelist() if self.dp else []
        if self.RECYCLE_REF not in wl:
            pairs = list(pairs) + [(self.RECYCLE_REF, self.timeframe)]
        return pairs

    # ------------------------------------------------------------------ signal
    @staticmethod
    def _recycle_series(closes: pd.Series, ts: pd.Timestamp,
                        sma_window: int, hysteresis: int) -> bool | None:
        """Pure signal computation — unit-testable without freqtrade.

        closes: BTC 1h close series, DatetimeIndex tz-aware UTC, ALREADY
        sliced to candles strictly before ts (causality is the caller's
        slicing). Returns recycle_on for time ts, or None when the closed
        daily history is too short for SMA(sma_window).
        """
        if closes is None or len(closes) == 0:
            return None
        daily = closes.resample("1D").last()
        # keep only fully-closed UTC days: bin [D, D+1) closed iff ts >= D+1
        while len(daily) and (daily.index[-1] + pd.Timedelta(days=1)) > ts:
            daily = daily.iloc[:-1]
        if len(daily) < sma_window:
            return None
        sma = daily.rolling(sma_window).mean()
        raw = (daily <= sma) & sma.notna() & daily.notna()   # NaN -> no signal
        if hysteresis <= 0:
            return bool(raw.iloc[-1])
        # confirmation state machine: flip ON (OFF) only after the raw
        # condition has held for hysteresis+1 consecutive days
        state = False
        on_run = 0
        off_run = 0
        for v in raw:
            if v:
                on_run += 1
                off_run = 0
                if not state and on_run > hysteresis:
                    state = True
            else:
                off_run += 1
                on_run = 0
                if state and off_run > hysteresis:
                    state = False
        return state

    def _recycle_on(self, current_time: datetime) -> bool:
        """Recycle state at current_time; False unless PROVEN on (causal,
        NaN-warmup conservative).

        Data source note: the natural candidate get_analyzed_dataframe is
        UNUSABLE for a daily SMA100 in this freqtrade (2026.8): in backtest it
        returns only the last MAX_DATAFRAME_CANDLES=1000 candles up to now
        (~42 days of 1h — the very trap behind OPT8's latent stop bug), so the
        resampled daily series would never reach 100 closed days and the
        signal would silently stay off (verified empirically: first 1.28 run
        came out trade-identical to the baseline). get_pair_dataframe is the
        freqtrade-blessed causal accessor for callbacks: in backtest it
        returns the RAW frame from the start of loaded history, cut at
        timeframe_to_prev_date(1h, current time) by freqtrade itself
        ("necessary to prevent lookahead bias in callbacks"), and we only read
        the raw 'close' column (no indicators needed). We ADDITIONALLY slice
        strictly before current_time ourselves, which drops the just-opened
        current candle that freqtrade's floor-to-candle cutoff keeps.
        """
        if self.dp is None:
            return False
        df = self.dp.get_pair_dataframe(self.RECYCLE_REF, self.timeframe)
        if df is None or len(df) == 0:
            return False
        # tz/unit normalization (d09ba64 lesson): tz-aware UTC, ms grid
        ts = pd.Timestamp(current_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        idx = int(df["date"].searchsorted(ts.floor("ms"))) - 1
        if idx < 24 * 30:   # under a month of 1h data -> certainly no SMA100
            return False
        key = (len(df), idx, int(self.RECYCLE_SMA), int(self.RECYCLE_HYSTERESIS_DAYS))
        if self._recycle_state_cache is not None and self._recycle_state_cache[0] == key:
            return self._recycle_state_cache[1]
        closes = df["close"].iloc[: idx + 1]
        closes.index = pd.DatetimeIndex(df["date"].iloc[: idx + 1])
        state = self._recycle_series(closes, ts, int(self.RECYCLE_SMA),
                                     int(self.RECYCLE_HYSTERESIS_DAYS))
        on = bool(state) if state is not None else False   # warmup -> OFF
        self._recycle_state_cache = (key, on)
        return on

    # ------------------------------------------------------------------ sizing
    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        stake = super().custom_stake_amount(pair, current_time, current_rate,
                                            proposed_stake, min_stake, max_stake,
                                            leverage, entry_tag, side, **kwargs)
        if float(self.RECYCLE_MULT) == 1.0:
            return stake                       # regression mode: untouched
        try:
            if self._recycle_on(current_time):
                stake = stake * float(self.RECYCLE_MULT)
                if max_stake:
                    stake = min(stake, max_stake)
        except Exception:
            logger.warning("OPT9_Recycle signal failed for %s at %s: sizing "
                           "passed through unamplified", pair, current_time)
            return stake
        return stake


# --- run variants (pre-registered points; see research_ab/CONTEXT.md) -------
class OPT9_Recycle_M10(OPT9_Recycle):
    """Multiplier identity — MUST reproduce OPT9_VolatilitySystem trade-for-trade
    (regression test that the overlay cannot change behavior at MULT=1.0)."""
    RECYCLE_MULT = 1.0


class OPT9_Recycle_M156(OPT9_Recycle):
    """Full recycle: A absorbs B's whole 36% -> 100/64 = 1.5625 (rounded 1.56)."""
    RECYCLE_MULT = 1.56
