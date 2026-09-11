# Strategy v2 - Donchian channel breakout (classic turtle-style), long & short.
# Freqtrade futures (isolated), timeframe 1h.
#
# Entry:  close breaks above the highest high of the previous N_entry candles
#         (channel computed on candles shifted by 1 -> only closed candles)
#         AND 4h trend filter agrees (close above/below 4h EMA200)
#         AND ADX > adx_min
# Exit:   close crosses the opposite M_exit channel line (signal exit),
#         ATR initial stop + ATR trailing stop, time stop.
# Sizing: risk-based (~1% equity per trade), leverage fixed 3x.
# No martingale, no position adding, no grid.
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    informative,
    stoploss_from_absolute,
)


class DonchianBreakoutV2(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True

    # 200 x 4h informative EMA needs ~800 1h candles; breakout lookback needs <=168.
    startup_candle_count: int = 999

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    minimal_roi = {"0": 100.0}
    stoploss = -0.30  # catastrophe backstop only
    use_custom_stoploss = True
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # ======================= tunable parameters =======================
    entry_lookback = IntParameter(48, 168, default=96, space="buy")
    exit_lookback = IntParameter(24, 72, default=48, space="sell")
    adx_min = IntParameter(15, 25, default=18, space="buy")
    use_trend_filter = True  # 4h EMA200 directional filter
    atr_period = 14
    atr_stop_mult = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.0, 3.0, default=2.0, decimals=1, space="sell")
    risk_pct = 0.01
    leverage_fixed = 3
    time_stop_hours = 24 * 21
    # ===================================================================

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200_4h"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def informative_pairs(self):
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # The @informative decorator above merged the 4h EMA200 into this 1h frame;
        # 4h values only become visible after the 4h candle has closed (no lookahead).
        if "ema200_4h_4h" in dataframe.columns:
            dataframe["trend_4h"] = dataframe["ema200_4h_4h"]

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)

        lb = int(self.entry_lookback.value)
        xb = int(self.exit_lookback.value)
        # Channel of the PREVIOUS lb candles (shift(1) => no lookahead by construction).
        dataframe["dc_high"] = dataframe["high"].rolling(lb).max().shift(1)
        dataframe["dc_low"] = dataframe["low"].rolling(lb).min().shift(1)
        dataframe["dc_exit_high"] = dataframe["high"].rolling(xb).max().shift(1)
        dataframe["dc_exit_low"] = dataframe["low"].rolling(xb).min().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_trend_ok = (dataframe["close"] > dataframe["trend_4h"]) if self.use_trend_filter else True
        short_trend_ok = (dataframe["close"] < dataframe["trend_4h"]) if self.use_trend_filter else True
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["dc_high"])
                & long_trend_ok
                & (dataframe["adx"] > self.adx_min.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["dc_low"])
                & short_trend_ok
                & (dataframe["adx"] > self.adx_min.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["dc_exit_low"])
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["dc_exit_high"])
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        return dataframe

    # ------------------------------------------------------------------ helpers
    def _signal_candle(self, pair: str, until: datetime):
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
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            stop_pct = float(self.atr_stop_mult.value) * float(row["atr"]) / float(row["close"])
            stop_pct = max(stop_pct, 0.005)
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = notional / max(leverage, 1.0)
            stake = min(stake, equity * 0.35, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
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
            return stoploss_from_absolute(min(initial_stop, trail_stop), current_rate, is_short=True, leverage=lev)
        else:
            initial_stop = trade.open_rate - self.atr_stop_mult.value * atr_entry
            extreme = trade.max_rate or trade.open_rate
            trail_stop = extreme - self.atr_trail_mult.value * atr_entry
            return stoploss_from_absolute(max(initial_stop, trail_stop), current_rate, is_short=False, leverage=lev)

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        if current_time - trade.open_date_utc > timedelta(hours=self.time_stop_hours):
            return "time_stop"
        return None
