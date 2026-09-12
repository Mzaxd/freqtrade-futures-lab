# Standalone versions of the three routed sub-strategies (for the routing-gain
# test): identical logic to the router legs but WITHOUT any regime gating or
# regime-based exits - each runs alone on the same data. 4h timeframe.
#   TrendLongSA  - EMA-alignment long engine (wide trailing)
#   TrendShortSA - EMA-alignment short engine
#   MeanRevSA    - Bollinger z-rejection mean reversion (anchored stop, no trail)
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class _SubBase(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 400

    order_types = {"entry": "market", "exit": "market", "stoploss": "market",
                   "stoploss_on_exchange": False}
    minimal_roi = {"0": 100.0}
    stoploss = -0.30
    use_custom_stoploss = True
    use_exit_signal = True
    position_adjustment_enable = False

    RISK = 0.010
    ATR_STOP = 3.0
    ATR_TRAIL = 4.2
    TIME_H = 24 * 28
    EMA_FAST, EMA_SLOW, EMA_TREND = 20, 50, 200
    ADX_MIN = 18

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["ef"] = ta.EMA(dataframe, timeperiod=self.EMA_FAST)
        dataframe["es"] = ta.EMA(dataframe, timeperiod=self.EMA_SLOW)
        dataframe["et"] = ta.EMA(dataframe, timeperiod=self.EMA_TREND)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def _signal_candle(self, pair: str, until: datetime):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3, max_leverage)

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            stop_pct = max(self.ATR_STOP * float(row["atr"]) / float(row["close"]), 0.005)
            equity = self.wallets.get_total_stake_amount()
            stake = equity * self.RISK / stop_pct / max(leverage, 1.0)
            stake = min(stake, equity * 0.35, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def _atr_at_entry(self, pair, trade):
        df, idx = self._signal_candle(pair, trade.open_date_utc)
        return float(df.iloc[idx]["atr"])

    def custom_exit_time(self, trade, current_time):
        if current_time - trade.open_date_utc > timedelta(hours=self.TIME_H):
            return "time_stop"
        return None


class TrendLongSA(_SubBase):
    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ef"] > dataframe["es"])
            & (dataframe["close"] > dataframe["et"])
            & (dataframe["adx"] > self.ADX_MIN)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["ef"] < dataframe["es"]) & (dataframe["volume"] > 0),
                      "exit_long"] = 1
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        try:
            atr = self._atr_at_entry(pair, trade)
        except Exception:
            return None
        if atr <= 0:
            return None
        initial = trade.open_rate - self.ATR_STOP * atr
        extreme = trade.max_rate or trade.open_rate
        trail = extreme - self.ATR_TRAIL * atr
        return stoploss_from_absolute(max(initial, trail), current_rate,
                                      is_short=False, leverage=trade.leverage or 1.0)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        return self.custom_exit_time(trade, current_time)


class TrendShortSA(_SubBase):
    RISK = 0.007
    TIME_H = 24 * 21

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ef"] < dataframe["es"])
            & (dataframe["close"] < dataframe["et"])
            & (dataframe["adx"] > self.ADX_MIN)
            & (dataframe["volume"] > 0),
            "enter_short",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["ef"] > dataframe["es"]) & (dataframe["volume"] > 0),
                      "exit_short"] = 1
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        try:
            atr = self._atr_at_entry(pair, trade)
        except Exception:
            return None
        if atr <= 0:
            return None
        initial = trade.open_rate + self.ATR_STOP * atr
        extreme = trade.min_rate or trade.open_rate
        trail = extreme + self.ATR_TRAIL * atr
        return stoploss_from_absolute(min(initial, trail), current_rate,
                                      is_short=True, leverage=trade.leverage or 1.0)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        return self.custom_exit_time(trade, current_time)


class MeanRevSA(_SubBase):
    can_short = True
    RISK = 0.005
    ATR_STOP = 2.0
    ATR_TRAIL = None
    TIME_H = 24 * 7
    BB_PERIOD = 30
    BB_STD = 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        mid = ta.SMA(dataframe, timeperiod=self.BB_PERIOD)
        std = dataframe["close"].rolling(self.BB_PERIOD).std()
        z = (dataframe["close"] - mid) / std
        dataframe["bb_mid"] = mid
        dataframe.loc[(z.shift(1) <= -self.BB_STD) & (z > -self.BB_STD)
                      & (dataframe["volume"] > 0), "enter_long"] = 1
        dataframe.loc[(z.shift(1) >= self.BB_STD) & (z < self.BB_STD)
                      & (dataframe["volume"] > 0), "enter_short"] = 1
        dataframe.loc[(dataframe["close"] > mid) & (dataframe["close"].shift(1) <= mid.shift(1)),
                      "exit_long"] = 1
        dataframe.loc[(dataframe["close"] < mid) & (dataframe["close"].shift(1) >= mid.shift(1)),
                      "exit_short"] = 1
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe  # signals set in populate_indicators

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        try:
            atr = self._atr_at_entry(pair, trade)
        except Exception:
            return None
        if atr <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            stop = trade.open_rate + self.ATR_STOP * atr
            return stoploss_from_absolute(stop, current_rate, is_short=True, leverage=lev)
        stop = trade.open_rate - self.ATR_STOP * atr
        return stoploss_from_absolute(stop, current_rate, is_short=False, leverage=lev)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        return self.custom_exit_time(trade, current_time)
