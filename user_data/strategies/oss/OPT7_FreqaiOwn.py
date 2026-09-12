# OPT7_FreqaiOwn.py — Phase 7 S4 (Agent-S4): FreqAI own-feature fork of ND_FreqaiExampleLgbm
#
# Fork delta vs ND template (logic otherwise identical, label unchanged: &-s_close
# regression on future 20x15m mean return):
#   * optional own features (selected via env OPT7_FEATURES, comma list):
#       - funding  : causal funding rate (opt_common.attach_funding, last SETTLED
#                    rate, no lookahead) + 3-day mean of it
#       - regime   : BTC 4h EMA200 trend state (close vs EMA200, binary + relative
#                    distance), merged backward at 4h candle CLOSE time (dates
#                    shifted +4h before merge_asof so an unfinished 4h candle is
#                    never visible to a 15m candle)
#       - volq     : ATR(14) percentile rank over trailing 30d (2880 x 15m)
#   * entry threshold via env OPT7_THRESHOLD (default 0.02)
#   * volq uses rolling(2880, min_periods=1440).rank(pct=True): freqtrade caps
#     strategy startup_candle_count at ~5x exchange ohlcv limit (2494), so the
#     full 30d rank window cannot be fully warmed for the FIRST training window
#     only (~first 15d of its 30d use a >=15d window instead). All later
#     windows rank over the full 30d. startup stays 40 as in ND.
#
# Pre-registered experiment matrix (frozen before first 2023 run):
#   A0: OPT7_FEATURES=""                thr 0.02  (fork-equivalence vs ND T2)
#   A1: OPT7_FEATURES="funding"         thr 0.02
#   A2: OPT7_FEATURES="regime"          thr 0.02
#   A3: OPT7_FEATURES="funding,regime,volq" thr 0.02
#   then threshold sweep {0.03, 0.05} and retrain 14d at the best combo.

from __future__ import annotations

import logging
import os
from functools import reduce

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy

import opt_common  # same-dir helper (phase-1, DO NOT MODIFY): causal funding attach

logger = logging.getLogger(__name__)

OPT7_FEATURES = {f.strip() for f in os.environ.get("OPT7_FEATURES", "").split(",") if f.strip()}
OPT7_THRESHOLD = float(os.environ.get("OPT7_THRESHOLD", "0.02"))
logger.info("OPT7_FreqaiOwn active config: features=%s threshold=%s", sorted(OPT7_FEATURES), OPT7_THRESHOLD)

BTC_4H_PAIR = "BTC/USDT:USDT"
FOUR_H = pd.Timedelta(hours=4)
VOLQ_WINDOW = 2880  # 30d of 15m candles
FUNDING_MA_CANDLES = 288  # 3d of 15m candles ~ 9 funding settlements


class OPT7_FreqaiOwn(IStrategy):
    """
    FreqAI LightGBM regression, ND template base features (~90) plus optional
    own features (funding / BTC 4h regime / vol quantile). Regression label
    unchanged. Research fork, not production.
    """

    minimal_roi = {"0": 0.1, "240": -1}

    plot_config = {
        "main_plot": {},
        "subplots": {
            "&-s_close": {"&-s_close": {"color": "blue"}},
            "do_predict": {
                "do_predict": {"color": "brown"},
            },
        },
    }

    process_only_new_candles = True
    stoploss = -0.05
    use_exit_signal = True
    # as ND template (40); freqtrade rejects >2494 for live-fetch reasons and
    # FreqAI data loading adds train_period on top anyway (see module header).
    startup_candle_count: int = 40
    can_short = True
    timeframe = "15m"

    # ---------------- base features: identical to ND template ----------------

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-sma-period"] = ta.SMA(dataframe, timeperiod=period)
        dataframe["%-ema-period"] = ta.EMA(dataframe, timeperiod=period)

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=period, stds=2.2
        )
        dataframe["bb_lowerband-period"] = bollinger["lower"]
        dataframe["bb_middleband-period"] = bollinger["mid"]
        dataframe["bb_upperband-period"] = bollinger["upper"]

        dataframe["%-bb_width-period"] = (
            dataframe["bb_upperband-period"] - dataframe["bb_lowerband-period"]
        ) / dataframe["bb_middleband-period"]
        dataframe["%-close-bb_lower-period"] = dataframe["close"] / dataframe["bb_lowerband-period"]

        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)

        dataframe["%-relative_volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_price"] = dataframe["close"]
        return dataframe

    # ---------------- own features (own pair, base tf, unshifted) ------------

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        dataframe["%-hour_of_day"] = dataframe["date"].dt.hour

        pair = metadata.get("pair", "")

        if "funding" in OPT7_FEATURES:
            # causal: rate of the settlement BEFORE the latest settled one
            dataframe = opt_common.attach_funding(dataframe, pair)
            dataframe["%-funding_rate"] = dataframe["funding_rate"]
            dataframe["%-funding_ma3d"] = dataframe["funding_rate"].rolling(
                FUNDING_MA_CANDLES
            ).mean()
            dataframe = dataframe.drop(columns=["funding_rate"])

        if "regime" in OPT7_FEATURES:
            dataframe = self._add_btc4h_regime(dataframe)

        if "volq" in OPT7_FEATURES:
            atr = ta.ATR(dataframe, timeperiod=14)
            dataframe["%-atr_pctl_30d"] = atr.rolling(
                VOLQ_WINDOW, min_periods=VOLQ_WINDOW // 2
            ).rank(pct=True)

        return dataframe

    def _add_btc4h_regime(self, dataframe: DataFrame) -> DataFrame:
        """BTC 4h EMA200 trend state, causal merge at 4h candle close time."""
        btc = self.dp.get_pair_dataframe(BTC_4H_PAIR, "4h")
        if btc is None or btc.empty:
            raise RuntimeError(
                f"OPT7: no 4h dataframe for {BTC_4H_PAIR} — regime features unavailable"
            )
        btc = btc.copy()
        btc["ema200"] = ta.EMA(btc, timeperiod=200)
        btc["regime"] = (btc["close"] > btc["ema200"]).astype("float64")
        btc["dist"] = btc["close"] / btc["ema200"] - 1.0

        left = dataframe[["date"]].copy()
        left["date"] = (
            pd.to_datetime(left["date"], utc=True).astype("datetime64[us, UTC]")
        )
        right = btc[["date", "regime", "dist"]].copy()
        right["date"] = (
            pd.to_datetime(right["date"], utc=True).astype("datetime64[us, UTC]") + FOUR_H
        )  # 4h candle becomes visible only at its close; prevents lookahead
        merged = pd.merge_asof(
            left.sort_values("date"), right.sort_values("date"), on="date", direction="backward"
        )
        dataframe["%-btc4h_regime"] = merged["regime"].to_numpy()
        dataframe["%-btc4h_dist"] = merged["dist"].to_numpy()
        return dataframe

    # ---------------- label & pipeline: identical to ND template -------------

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["&-s_close"] = (
            dataframe["close"]
            .shift(-self.freqai_info["feature_parameters"]["label_period_candles"])
            .rolling(self.freqai_info["feature_parameters"]["label_period_candles"])
            .mean()
            / dataframe["close"]
            - 1
        )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        enter_long_conditions = [
            df["do_predict"] == 1,
            df["&-s_close"] > OPT7_THRESHOLD,
        ]

        if enter_long_conditions:
            df.loc[
                reduce(lambda x, y: x & y, enter_long_conditions), ["enter_long", "enter_tag"]
            ] = (1, "long")

        enter_short_conditions = [
            df["do_predict"] == 1,
            df["&-s_close"] < -OPT7_THRESHOLD,
        ]

        if enter_short_conditions:
            df.loc[
                reduce(lambda x, y: x & y, enter_short_conditions), ["enter_short", "enter_tag"]
            ] = (1, "short")

        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        exit_long_conditions = [df["do_predict"] == 1, df["&-s_close"] < 0]
        if exit_long_conditions:
            df.loc[reduce(lambda x, y: x & y, exit_long_conditions), "exit_long"] = 1

        exit_short_conditions = [df["do_predict"] == 1, df["&-s_close"] > 0]
        if exit_short_conditions:
            df.loc[reduce(lambda x, y: x & y, exit_short_conditions), "exit_short"] = 1

        return df

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = df.iloc[-1].squeeze()

        if side == "long":
            if rate > (last_candle["close"] * (1 + 0.0025)):
                return False
        else:
            if rate < (last_candle["close"] * (1 - 0.0025)):
                return False

        return True
