"""OPT8b_VolatilitySystem — run-3 hotfix candidate for the LIVE OPT8 (2026-11-01).

Second latent bug found in OPT8 (the first was the microsecond timestamp,
fixed before run-2). Root cause of this one:

  OPT8.custom_stoploss re-looks-up the entry candle every call via
  dp.get_analyzed_dataframe. In backtest, freqtrade >=2024 returns only the
  last MAX_DATAFRAME_CANDLES (1000) candles; in live/dry the analyzed
  dataframe is likewise a rolling window. Once a trade is held longer than
  that window (~42 days at 1h), _signal_candle returns -1 ("no candle
  before entry") and custom_stoploss returns fallback_stop_ratio = -0.10
  AS A RAW RATIO. adjust_stop_loss interprets raw ratios relative to the
  CURRENT price -> the stop jumps to current*0.95 and ratchets with every
  new high: an unintended 5% trailing stop that fires exactly (and only)
  on long-held trend winners. 12p IS replay: OPT4 +1464% -> OPT8 +1171%
  with 15 big winners truncated (ETH stop pulled to +131% of entry, AVAX
  to +207%). Dry-run run-2 (started 2026-09-25) hits this on any trade
  that survives ~1000 hours.

Fix (signal logic, sizing, risk model unchanged from OPT4/OPT8):
  1. entry ATR looked up ONCE at the first stoploss call (entry candle is
     always fresh then) and cached on the trade (set_custom_data —
     persisted across restarts in live mode);
  2. fallback (cache and lookup both unavailable) is a STATIC tight stop
     anchored at the ENTRY price via stoploss_from_open — the semantics
     the OPT8 docstring always intended ("TIGHT static stop (-0.10)"),
     never a current-price-relative trailing stop.

Replay equivalence: on the 12p IS window this class reproduces the frozen
OPT4 benchmark (see opt9 program logs) because the fixed path is inert
while the entry candle is inside the window and never ages out.
"""
from datetime import datetime

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute, stoploss_from_open

from OPT8_VolatilitySystem import OPT8_VolatilitySystem


class OPT8b_VolatilitySystem(OPT8_VolatilitySystem):
    anchor_cache_key = "opt8b_atr_entry"

    def _anchored_atr(self, trade: Trade) -> float | None:
        cached = trade.get_custom_data(self.anchor_cache_key)
        if cached is not None:
            return float(cached)
        df, idx = self._signal_candle(trade.pair, trade.open_date_utc)
        if idx < 0:
            return None
        atr = float(df.iloc[idx]["atr_raw"])
        if atr != atr or atr <= 0:
            return None
        trade.set_custom_data(self.anchor_cache_key, atr)
        return atr

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        lev = trade.leverage or 1.0
        atr_entry = self._anchored_atr(trade)
        if atr_entry is None:
            return stoploss_from_open(self.fallback_stop_ratio, current_rate,
                                      is_short=trade.is_short, leverage=lev)
        if trade.is_short:
            stop_price = trade.open_rate + self.stop_atr_mult.value * atr_entry
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=lev)
        stop_price = trade.open_rate - self.stop_atr_mult.value * atr_entry
        return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=lev)
