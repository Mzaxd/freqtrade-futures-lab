# OPT7_SuperDD_B — Phase-7 S3 salvage variant B of oss/Supertrend.py.
#
# Signal core PRESERVED from Supertrend.py (spot main-dir version):
#   entry = 3 buy-side supertrends all 'up'  (params m/p: 4/8, 7/9, 1/8 — untouched)
#   exit  = 3 sell-side supertrends all 'down' (params m/p: 1/16, 3/18, 6/18 — untouched)
# Only the 6 needed supertrend columns are computed (the original builds the whole
# 630-column hyperopt grid; the 6 selected columns are grid-independent — verified
# separately). startup_candle_count=199 kept identical to the original.
#
# Risk structure REPLACED (the S3 "treat the 52.3% DD" payload, lab paradigm
# OPT1_VolatilitySystem / TrendBaselineV1):
#   - ROI disabled ({"0": 100}) and freqtrade trailing_stop removed; exits =
#     signal exit / ATR stop / catastrophe cap.
#   - stoploss = -0.30 catastrophe backstop only.
#   - Variant B = A + chandelier ATR trailing: stop_price = max(entry - 2.0*ATR_e,
#     trade.max_rate - trail_atr_mult*ATR_e) with trail_atr_mult = 2.0 (stop can
#     only tighten — freqtrade ratchets custom stops).
#   - 1%-equity-risk sizing: notional = equity * 0.01 / stop_pct with
#     stop_pct = max(stop_atr_mult * ATR_entry / close, 0.005); stake capped at
#     35% of equity. Leverage fixed 1x (same as original in futures isolated).
#   - No DCA (position_adjustment_enable = False).
#
# Evaluation: optimization pool 20210101-20240101 only (12 old coins / 6 half-year
# subwindows / 11 new coins), then one-shot holdout after freeze. See
# research_openstrat/reports/phase7_s3_supertrend.md.
from datetime import datetime

import talib.abstract as ta
import technical.indicators as ftt
from pandas import DataFrame, Series

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class OPT7_SuperDD_B(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count: int = 199

    # original Supertrend.py hyperopt values — frozen signal core
    buy_st = [(4, 8), (7, 9), (1, 8)]
    sell_st = [(1, 16), (3, 18), (6, 18)]

    # risk structure (replaces ROI table + SL -0.265 + freqtrade trailing of the original)
    minimal_roi = {"0": 100}
    stoploss = -0.30
    use_custom_stoploss = True
    trailing_stop = False
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # risk model constants
    risk_pct = 0.01          # risk per trade as fraction of equity
    stop_atr_mult = 6.0      # initial stop distance in ATR multiples (pool probe r2)
    trail_atr_mult = 6.0     # chandelier trail distance in entry-ATR multiples (pool probe r2)
    stop_pct_floor = 0.005   # minimum stop distance 0.5%
    margin_cap = 0.35        # max stake per position as fraction of equity
    atr_period = 14

    def informative_pairs(self):
        return []

    # ------------------------------------------------------------------ helpers
    def _signal_candle(self, pair: str, until: datetime) -> tuple[DataFrame, int]:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def _st_dir(self, dataframe: DataFrame, multiplier: int, period: int) -> Series:
        _, stx = ftt.supertrend(dataframe, period=period, multiplier=multiplier)
        return Series(stx, index=dataframe.index).fillna("")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for i, (m, p) in enumerate(self.buy_st, start=1):
            dataframe[f"st_buy_{i}"] = self._st_dir(dataframe, m, p)
        for i, (m, p) in enumerate(self.sell_st, start=1):
            dataframe[f"st_sell_{i}"] = self._st_dir(dataframe, m, p)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=self.atr_period)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["st_buy_1"] == "up")
                & (dataframe["st_buy_2"] == "up")
                & (dataframe["st_buy_3"] == "up")
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["st_sell_1"] == "down")
                & (dataframe["st_sell_2"] == "down")
                & (dataframe["st_sell_3"] == "down")
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe

    # ------------------------------------------------------------------ sizing
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return 1.0

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            atr = float(row["atr14"])
            close = float(row["close"])
            if not atr or atr <= 0 or not close or close <= 0:
                return proposed_stake
            stop_pct = max(self.stop_atr_mult * atr / close, self.stop_pct_floor)
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = min(notional, equity * self.margin_cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    # ------------------------------------------------------------------ stop
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        # variant B: initial ATR stop + chandelier ATR trailing off trade.max_rate
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr14"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        peak = trade.max_rate or trade.open_rate
        stop_price = max(
            trade.open_rate - self.stop_atr_mult * atr_entry,
            peak - self.trail_atr_mult * atr_entry,
        )
        return stoploss_from_absolute(
            stop_price, current_rate, is_short=trade.is_short, leverage=trade.leverage or 1.0
        )
