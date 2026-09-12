# OPT7_SuperFusion — Phase-7 S3 vote-fusion variant (Supertrend.py x FSupertrendStrategy.py).
#
# Fusion semantics (declared: enter only when BOTH parents agree, exit on EITHER
# parent's reversal):
#   - Entry: both parents' long entries require the same 3 buy-side supertrends
#     'up' with IDENTICAL frozen params (m/p: 4/8, 7/9, 1/8 — both files carry
#     the same buy_params), so "both agree" == the common 3-ST-up condition.
#   - Exit: spot version (Supertrend.py) exits when ALL 3 sell-side STs are down
#     (1/16, 3/18, 6/18); futures version (FSupertrendStrategy.py) exits long when
#     supertrend_2_sell m2/p2 = 3/18 alone is down. "Either reversal" is therefore
#     the UNION == the single 3/18 flip (the 3-ST consensus is a subset of it).
#   Net effect vs SuperDD core: same entries, structurally earlier exits.
#
# Risk structure: same payload as OPT7_SuperDD_A final (catastrophe -0.30,
# ATR-anchored initial stop stop_atr_mult=8.0, NO trailing (pool evidence: trailing
# harms this family), 1%-equity-risk sizing, ROI off, 1x, no DCA).
from datetime import datetime

import talib.abstract as ta
import technical.indicators as ftt
from pandas import DataFrame, Series

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class OPT7_SuperFusion(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count: int = 199

    # frozen signal core (shared by both parents)
    buy_st = [(4, 8), (7, 9), (1, 8)]
    sell_st = [(1, 16), (3, 18), (6, 18)]

    # risk structure (OPT7_SuperDD_B payload)
    minimal_roi = {"0": 100}
    stoploss = -0.30
    use_custom_stoploss = True
    trailing_stop = False
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    risk_pct = 0.01
    stop_atr_mult = 8.0
    stop_pct_floor = 0.005
    margin_cap = 0.35
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
        # both parents agree (identical entry definitions)
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
        # exit on EITHER parent's reversal: futures parent (st_sell_2 = 3/18 flip)
        # subsumes the spot parent's 3-ST consensus
        dataframe.loc[
            (
                (dataframe["st_sell_2"] == "down")
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
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr14"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        stop_price = trade.open_rate - self.stop_atr_mult * atr_entry
        return stoploss_from_absolute(
            stop_price, current_rate, is_short=trade.is_short, leverage=trade.leverage or 1.0
        )
