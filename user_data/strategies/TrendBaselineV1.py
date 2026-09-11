# Strategy v1 - Trend-following baseline (EMA cross + trend filter + ADX)
# Freqtrade futures (isolated), timeframe 1h, long & short.
#
# Entry:  EMA(fast) crosses above EMA(slow)  AND close > EMA(trend)  AND ADX > adx_min  -> long
#         EMA(fast) crosses below EMA(slow)  AND close < EMA(trend)  AND ADX > adx_min  -> short
# Exit:   opposite EMA cross (signal), ATR initial stop + ATR trailing stop (custom_stoploss),
#         time stop (custom_exit), hard catastrophe stoploss cap.
# Sizing: risk-based via custom_stake_amount: equity * risk_pct / stop_distance_pct / leverage
#         -> per-trade risk ~1% of equity. Leverage fixed at 3x (<= requirement of 3x initial).
# No martingale, no position adding, no grid. Only closed candles are used (freqtrade signal
# semantics: signals on candle t are acted on at open of t+1; all rolling indicators are
# computed on closed candles only).
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    stoploss_from_absolute,
)


class TrendBaselineV1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True

    startup_candle_count: int = 400  # EMA200 + buffer

    # --- Orders: market orders on both sides => conservative taker fee on every fill ---
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Disable ROI-based exits; exits come from signal / stop / trailing / time stop.
    minimal_roi = {"0": 100.0}

    # Catastrophe backstop only (price-move terms; with 3x leverage ~= 10% price move).
    stoploss = -0.30
    use_custom_stoploss = True

    # No position adjustment (no martingale / no averaging).
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # ======================= tunable parameters (single place) =======================
    # EMA periods
    ema_fast = 20
    ema_slow = 50
    ema_trend = 200
    # ADX trend-strength filter
    adx_min = IntParameter(15, 30, default=20, space="buy")
    # ATR stop / trailing
    atr_period = 14
    atr_stop_mult = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="sell")
    # risk per trade as fraction of equity
    risk_pct = 0.01
    # fixed leverage (never above 3)
    leverage_fixed = 3
    # time stop: close trade after this many hours if still open
    time_stop_hours = 24 * 28
    # ==================================================================================

    def informative_pairs(self):
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["adx"] > self.adx_min.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["close"] < dataframe["ema_trend"])
                & (dataframe["adx"] > self.adx_min.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # trend break: fast EMA crosses back over slow EMA
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        return dataframe

    # ------------------------------------------------------------------ helpers
    def _signal_candle(self, pair: str, until: datetime) -> DataFrame:
        """Last candle strictly before `until` (the closed candle that generated the signal).
        get_analyzed_dataframe in backtesting returns the full precomputed frame; we only
        ever read rows at/before `until`, so no future data is used."""
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return min(self.leverage_fixed, max_leverage)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        # Risk-based sizing: notional such that (notional * stop_pct) = equity * risk_pct.
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            stop_pct = float(self.atr_stop_mult.value) * float(row["atr"]) / float(row["close"])
            stop_pct = max(stop_pct, 0.005)  # floor: at least 0.5% stop distance
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = notional / max(leverage, 1.0)
            # cap: never use more than 35% of equity as margin for one position
            stake = min(stake, equity * 0.35, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        # ATR stop anchored at entry; after favorable move, trail from extreme rate.
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            initial_stop = trade.open_rate + self.atr_stop_mult.value * atr_entry
            extreme = trade.min_rate or trade.open_rate
            trail_stop = extreme + self.atr_trail_mult.value * atr_entry
            stop_price = min(initial_stop, trail_stop)
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=lev)
        else:
            initial_stop = trade.open_rate - self.atr_stop_mult.value * atr_entry
            extreme = trade.max_rate or trade.open_rate
            trail_stop = extreme - self.atr_trail_mult.value * atr_entry
            stop_price = max(initial_stop, trail_stop)
            return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=lev)

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # time stop
        if current_time - trade.open_date_utc > timedelta(hours=self.time_stop_hours):
            return "time_stop"
        return None
