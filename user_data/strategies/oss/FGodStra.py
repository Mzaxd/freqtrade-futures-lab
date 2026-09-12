# FGodStra - Agent B minimal adaptation of GodStra (freqtrade-strategies repo)
# Original author: @Mablue (Masoud Azizi) - https://github.com/mablue/
# Adaptations for freqtrade 2026.8 + this lab (original GodStra.py left untouched):
#   1. `ta` package (add_all_ta_features) is NOT installed in this venv -> the 4
#      referenced indicator columns are computed with talib/pandas instead:
#        trend_ichimoku_base = (rolling_max(high,26)+rolling_min(low,26))/2   (ta-pkg definition)
#        volatility_kcc      = EMA((H+L+C)/3, 14)   (ta-pkg Keltner center; column
#                              is referenced by buy-cross-0 but never used by the
#                              '<R' operator, so exact parity does not affect signals)
#        trend_kst_diff      = KST(osc) - SMA(KST,9) with ta-pkg windows
#                              (roc 10/15/20/30, sma 10/10/10/15) - only used by '=R'
#        volume_mfi          = talib MFI(14) (sell-cross-0, unused by '=R' operator)
#   2. timeframe 12h -> 4h (no 12h data in this lab; 4h is the nearest available TF)
#   3. removed module-level print() and per-candle print(conditions) noise
#   4. removed unused `from numpy.lib import math` (breaks on numpy>=2)
# All trading params (buy/sell DNA dicts, ROI, stoploss, trailing) kept identical.

import logging
from functools import reduce

import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame

import talib.abstract as ta

logger = logging.getLogger(__name__)


class FGodStra(IStrategy):

    INTERFACE_VERSION: int = 3
    # Buy hyperspace params: (unchanged from original)
    buy_params = {
        'buy-cross-0': 'volatility_kcc',
        'buy-indicator-0': 'trend_ichimoku_base',
        'buy-int-0': 42,
        'buy-oper-0': '<R',
        'buy-real-0': 0.06295
    }

    # Sell hyperspace params: (unchanged from original)
    sell_params = {
        'sell-cross-0': 'volume_mfi',
        'sell-indicator-0': 'trend_kst_diff',
        'sell-int-0': 98,
        'sell-oper-0': '=R',
        'sell-real-0': 0.8779
    }

    # ROI table: (unchanged)
    minimal_roi = {
        "0": 0.3556,
        "4818": 0.21275,
        "6395": 0.09024,
        "22372": 0
    }

    # Stoploss: (unchanged)
    stoploss = -0.34549

    # Trailing stop: (unchanged)
    trailing_stop = True
    trailing_stop_positive = 0.22673
    trailing_stop_positive_offset = 0.2684
    trailing_only_offset_is_reached = True

    timeframe = '4h'  # original: '12h' (no 12h data in lab -> nearest available)

    startup_candle_count = 400

    def dna_size(self, dct: dict):
        def int_from_str(st: str):
            str_int = ''.join([d for d in st if d.isdigit()])
            if str_int:
                return int(str_int)
            return -1
        return len({int_from_str(digit) for digit in dct.keys()})

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # trend_ichimoku_base: (max(high,26)+min(low,26))/2
        dataframe['trend_ichimoku_base'] = (
            dataframe['high'].rolling(26).max() + dataframe['low'].rolling(26).min()
        ) / 2.0

        # volatility_kcc: Keltner channel center, EMA of typical price (14)
        tp = (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3.0
        dataframe['volatility_kcc'] = ta.EMA(tp, timeperiod=14)

        # trend_kst_diff: KST oscillator minus its signal line (ta-pkg ROC = ROCP*100)
        kst = (
            ta.SMA(ta.ROCP(dataframe, timeperiod=10) * 100, timeperiod=10) * 1
            + ta.SMA(ta.ROCP(dataframe, timeperiod=15) * 100, timeperiod=10) * 2
            + ta.SMA(ta.ROCP(dataframe, timeperiod=20) * 100, timeperiod=10) * 3
            + ta.SMA(ta.ROCP(dataframe, timeperiod=30) * 100, timeperiod=15) * 4
        )
        dataframe['trend_kst'] = kst
        dataframe['trend_kst_sig'] = ta.SMA(kst, timeperiod=9)
        dataframe['trend_kst_diff'] = dataframe['trend_kst'] - dataframe['trend_kst_sig']

        # volume_mfi (talib MFI, 14)
        dataframe['volume_mfi'] = ta.MFI(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = list()
        for i in range(self.dna_size(self.buy_params)):
            OPR = self.buy_params[f'buy-oper-{i}']
            IND = self.buy_params[f'buy-indicator-{i}']
            CRS = self.buy_params[f'buy-cross-{i}']
            INT = self.buy_params[f'buy-int-{i}']
            REAL = self.buy_params[f'buy-real-{i}']
            DFIND = dataframe[IND]
            DFCRS = dataframe[CRS]

            if OPR == ">":
                conditions.append(DFIND > DFCRS)
            elif OPR == "=":
                conditions.append(np.isclose(DFIND, DFCRS))
            elif OPR == "<":
                conditions.append(DFIND < DFCRS)
            elif OPR == "CA":
                conditions.append(qtpylib.crossed_above(DFIND, DFCRS))
            elif OPR == "CB":
                conditions.append(qtpylib.crossed_below(DFIND, DFCRS))
            elif OPR == ">I":
                conditions.append(DFIND > INT)
            elif OPR == "=I":
                conditions.append(DFIND == INT)
            elif OPR == "<I":
                conditions.append(DFIND < INT)
            elif OPR == ">R":
                conditions.append(DFIND > REAL)
            elif OPR == "=R":
                conditions.append(np.isclose(DFIND, REAL))
            elif OPR == "<R":
                conditions.append(DFIND < REAL)

        dataframe.loc[
            reduce(lambda x, y: x & y, conditions),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = list()
        for i in range(self.dna_size(self.sell_params)):
            OPR = self.sell_params[f'sell-oper-{i}']
            IND = self.sell_params[f'sell-indicator-{i}']
            CRS = self.sell_params[f'sell-cross-{i}']
            INT = self.sell_params[f'sell-int-{i}']
            REAL = self.sell_params[f'sell-real-{i}']
            DFIND = dataframe[IND]
            DFCRS = dataframe[CRS]

            if OPR == ">":
                conditions.append(DFIND > DFCRS)
            elif OPR == "=":
                conditions.append(np.isclose(DFIND, DFCRS))
            elif OPR == "<":
                conditions.append(DFIND < DFCRS)
            elif OPR == "CA":
                conditions.append(qtpylib.crossed_above(DFIND, DFCRS))
            elif OPR == "CB":
                conditions.append(qtpylib.crossed_below(DFIND, DFCRS))
            elif OPR == ">I":
                conditions.append(DFIND == INT)
            elif OPR == "=I":
                conditions.append(DFIND < INT)
            elif OPR == ">R":
                conditions.append(DFIND > REAL)
            elif OPR == "=R":
                conditions.append(np.isclose(DFIND, REAL))
            elif OPR == "<R":
                conditions.append(DFIND < REAL)

        dataframe.loc[
            reduce(lambda x, y: x & y, conditions),
            'exit_long'] = 1

        return dataframe
