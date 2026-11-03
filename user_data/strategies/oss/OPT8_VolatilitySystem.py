"""OPT8_VolatilitySystem — live-fix release of OPT4 (2026-09-25).

Root cause (dry-run run #1, 2026-09-12..23, archived as *_run1.sqlite):
OPT1._signal_candle did df["date"].searchsorted(trade.open_date_utc). Live fill
timestamps carry MICROSECOND precision (exchange fill times) while candle frames
are datetime64[ms]; pandas 3 raises "ValueError: Cannot losslessly convert
units" -> the bare `except` swallowed it -> custom_stoploss returned None (stop
stayed at the -0.30 catastrophe level) AND custom_stake_amount fell back to the
naive equal-split proposal. Backtest was immune because fills are candle-aligned
there (15:00:00.000). Consequence: 4 blown stops (-753/-361/-414/-642 USDT vs
~-100 design), realized -20.6% before shutdown.

Fixes in this file (signal logic unchanged from frozen OPT4):
 1. Floor the lookup timestamp to the frame's millisecond grid before
    searchsorted -> lossless conversion restored in live mode.
 2. _signal_candle no longer swallows: no earlier candle -> -1, callers act.
 3. custom_stoploss fallback: missing/NaN ATR -> log WARNING + TIGHT static
    stop (-0.10 ratio) instead of None (never fall back to the loose cap).
 4. custom_stake_amount fallback: log + halve the proposed stake.
 5. NaN ATR guard via pd.isna (the old `not atr` check lets NaN through).

Replay-validated against the run-#1 trade records: scripts/opt8_replay.py.
"""
import logging
from datetime import datetime

import pandas as pd
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

from OPT4_VolatilitySystem import OPT4_VolatilitySystem

logger = logging.getLogger(__name__)


class OPT8_VolatilitySystem(OPT4_VolatilitySystem):
    # tight fallback when the ATR anchor is unavailable (ratio incl. leverage)
    fallback_stop_ratio = -0.10

    def _signal_candle(self, pair: str, until: datetime) -> tuple[DataFrame, int]:
        """Analyzed dataframe and row index of the last candle strictly before
        `until`; -1 when no earlier candle exists (live rolling window)."""
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        ts = pd.Timestamp(until)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        # live fill times carry microseconds; candle frames are ms-resolution.
        # floor to ms so pandas 3 converts losslessly inside searchsorted.
        idx = int(df["date"].searchsorted(ts.floor("ms"))) - 1
        return df, idx

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        df, idx = self._signal_candle(pair, trade.open_date_utc)
        if idx < 0:
            logger.warning("OPT8 stop fallback (no candle before entry): %s", pair)
            return self.fallback_stop_ratio
        atr_entry = float(df.iloc[idx]["atr_raw"])
        if pd.isna(atr_entry) or atr_entry <= 0:
            logger.warning("OPT8 stop fallback (bad ATR %.6f): %s", atr_entry, pair)
            return self.fallback_stop_ratio
        lev = trade.leverage or 1.0
        if trade.is_short:
            stop_price = trade.open_rate + self.stop_atr_mult.value * atr_entry
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=lev)
        stop_price = trade.open_rate - self.stop_atr_mult.value * atr_entry
        return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=lev)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        def conservative() -> float:
            logger.warning("OPT8 sizing fallback (conservative halving): %s", pair)
            s = proposed_stake * 0.5
            s = min(s, max_stake) if max_stake else s
            if min_stake is not None:
                s = max(s, min_stake)
            return s

        df, idx = self._signal_candle(pair, current_time)
        if idx < 0:
            return conservative()
        row = df.iloc[idx]
        atr = float(row["atr_raw"])
        close = float(row["close"])
        if pd.isna(atr) or atr <= 0 or pd.isna(close) or close <= 0:
            return conservative()
        stop_pct = max(float(self.stop_atr_mult.value) * atr / close, self.stop_pct_floor)
        equity = self.wallets.get_total_stake_amount()
        notional = equity * self.risk_pct / stop_pct
        stake = notional / max(leverage, 1.0)
        stake = min(stake, equity * self.margin_cap, max_stake)
        if min_stake is not None:
            stake = max(stake, min_stake)
        return stake
