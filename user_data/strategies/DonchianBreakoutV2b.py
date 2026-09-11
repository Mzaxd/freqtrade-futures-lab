# v2.1 (DonchianBreakoutV2b) - single change vs v2: trading timeframe 1h -> 4h.
# The higher-timeframe trend filter moves from 4h EMA200 to 1d EMA200 to stay a
# *higher* timeframe than the strategy. Donchian lookbacks keep their bar-based
# meaning: entry_lookback=96 bars = 16 days, exit_lookback=48 bars = 8 days
# (classic turtle scale). Everything else identical to v2.
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import informative

from DonchianBreakoutV2 import DonchianBreakoutV2


class DonchianBreakoutV2b(DonchianBreakoutV2):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    startup_candle_count = 1200  # 200 days of 1d EMA => 1200 4h candles

    # neutralize the inherited 4h informative (same-TF merge is not meaningful here)
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200_1d"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if "ema200_1d_1d" in dataframe.columns:
            dataframe["trend_4h"] = dataframe["ema200_1d_1d"]  # alias keeps parent logic

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)

        lb = int(self.entry_lookback.value)
        xb = int(self.exit_lookback.value)
        dataframe["dc_high"] = dataframe["high"].rolling(lb).max().shift(1)
        dataframe["dc_low"] = dataframe["low"].rolling(lb).min().shift(1)
        dataframe["dc_exit_high"] = dataframe["high"].rolling(xb).max().shift(1)
        dataframe["dc_exit_low"] = dataframe["low"].rolling(xb).min().shift(1)
        return dataframe
