# Optimization experiment (iter-16): upstream Supertrend + classic slow-trend
# filter (only long while price is above the 1d EMA200). Zero fitted params.
# iter-15 (72h-momentum regime veto) hurt both windows and was rolled back.
from pandas import DataFrame

import talib.abstract as ta

from Supertrend import Supertrend as _Upstream

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from freqtrade.strategy import informative  # noqa: E402


class SupertrendMa(_Upstream):
    INTERFACE_VERSION = 3

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Upstream.populate_indicators(self, dataframe, metadata)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Upstream.populate_entry_trend(self, dataframe, metadata)
        veto = dataframe["close"] < dataframe["ema200_1d"]
        for col in ("enter_long", "enter_short"):
            if col in dataframe.columns:
                dataframe.loc[veto, col] = 0
        return dataframe
