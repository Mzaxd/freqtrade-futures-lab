# OPT1_VolatilitySystem — Phase-1 optimization of oss/VolatilitySystem.py (IS 2021-2022).
#
# Structural changes vs original (see research_openstrat/reports/phase1_volatilitysystem.md):
#   1. ATR stop replaces SL=-1: catastrophe cap stoploss=-0.30 + custom_stoploss anchored
#      at entry-time resampled ATR (stop_atr_mult * ATR_entry, long/short symmetric,
#      via stoploss_from_absolute). Raw resampled ATR (no 2.0 multiplier) is kept in
#      column 'atr_raw'; the signal multiplier is a hyperopt parameter instead.
#   2. Risk-based sizing (custom_stake_amount, aligned with lab risk model /
#      TrendBaselineV1): notional = equity * risk_pct / stop_pct where
#      stop_pct = stop_atr_mult * ATR_entry / close (floor 0.5%); stake = notional / 2
#      (fixed 2x leverage); margin capped at 35% of equity.
#   3. DCA removed: position_adjustment_enable = False. The 1%-risk semantics require the
#      stop distance to be fixed at entry; adding to a position would break the risk
#      budget (the add is sized off a stale stop distance). Lab convention: no averaging.
#   4. Hyperopt spaces: buy { signal_atr_mult, resample_hours }, sell { stop_atr_mult }.
#      NOTE: resample_hours is used inside populate_indicators, so hyperopt must run with
#      --analyze-per-epoch, otherwise indicators are computed once at defaults and the
#      resampled column names would not exist for other values.
#
# Only IS window 20210101-20230101 was used for every run behind these defaults.
from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    stoploss_from_absolute,
)

from technical.util import resample_to_interval, resampled_merge


class OPT1_VolatilitySystem(IStrategy):
    """
    Volatility breakout on resampled candles, with ATR stop + 1%-risk sizing.
    Based on https://www.tradingview.com/script/3hhs0XbR/ (via oss/VolatilitySystem.py).
    """

    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True

    # enough warmup for resample_hours<=6 * ATR(14) = 84 1h candles (+buffer)
    startup_candle_count: int = 200

    # market orders on both sides (conservative taker fees)
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # disable ROI exits; exits = reverse signal / ATR stop / catastrophe cap
    minimal_roi = {"0": 100}

    # 1. catastrophe backstop only; real stop is the ATR-anchored custom stop
    stoploss = -0.30
    use_custom_stoploss = True

    # 3. no DCA / no position adding
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # --- tunable parameters -----------------------------------------------------
    # defaults backfilled after IS hyperopt (plateau medians / best epoch):
    #   hyperopt: SharpeHyperOptLoss, --spaces buy sell, --random-state 42,
    #   --analyze-per-epoch (resample_hours lives in populate_indicators),
    #   --timerange 20210101-20230101, -j 2
    # signal: close_change > signal_atr_mult * ATR (resampled), long / < for short
    signal_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1, space="buy")
    # resample period (hours) for the volatility breakout
    resample_hours = IntParameter(2, 6, default=3, space="buy")
    # initial stop distance in multiples of entry-time resampled ATR
    stop_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1, space="sell")

    # risk model constants (fixed, not hyperopted)
    risk_pct = 0.01          # risk per trade as fraction of equity
    leverage_fixed = 2.0     # keep original 2x
    stop_pct_floor = 0.005   # minimum stop distance 0.5%
    margin_cap = 0.35        # max margin per position as fraction of equity
    # ------------------------------------------------------------------------------

    def informative_pairs(self):
        return []

    # ------------------------------------------------------------------ helpers
    def _signal_candle(self, pair: str, until: datetime) -> tuple[DataFrame, int]:
        """Analyzed dataframe and index of the last candle strictly before `until`
        (the signal candle; entry happens at the next candle's open)."""
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        resample_int = self.resample_hours.value * 60
        resampled = resample_to_interval(dataframe, resample_int)
        # raw ATR (NO multiplier) — used for both signal threshold and stop distance
        resampled["atr"] = ta.ATR(resampled, timeperiod=14)
        resampled["close_change"] = resampled["close"].diff()
        resampled["abs_close_change"] = resampled["close_change"].abs()

        dataframe = resampled_merge(dataframe, resampled, fill_na=True)
        # column names embed the resample interval -> build them dynamically
        dataframe["atr_raw"] = dataframe[f"resample_{resample_int}_atr"]
        dataframe["close_change"] = dataframe[f"resample_{resample_int}_close_change"]
        dataframe["abs_close_change"] = dataframe[f"resample_{resample_int}_abs_close_change"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        thr = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        dataframe.loc[dataframe["close_change"] > thr, "enter_long"] = 1
        dataframe.loc[dataframe["close_change"] * -1 > thr, "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # reverse signal closes the position
        dataframe.loc[dataframe["enter_long"] == 1, "exit_short"] = 1
        dataframe.loc[dataframe["enter_short"] == 1, "exit_long"] = 1
        return dataframe

    # ------------------------------------------------------------------ sizing
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return min(self.leverage_fixed, max_leverage)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        # 2. risk-based sizing: notional * stop_pct = equity * risk_pct
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            atr = float(row["atr_raw"])
            close = float(row["close"])
            if not atr or atr <= 0 or not close or close <= 0:
                return proposed_stake
            stop_pct = float(self.stop_atr_mult.value) * atr / close
            stop_pct = max(stop_pct, self.stop_pct_floor)
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = notional / max(leverage, 1.0)
            stake = min(stake, equity * self.margin_cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    # ------------------------------------------------------------------ stop
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        # initial stop anchored at the resampled ATR known at entry (no trailing)
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr_raw"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            stop_price = trade.open_rate + self.stop_atr_mult.value * atr_entry
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=lev)
        stop_price = trade.open_rate - self.stop_atr_mult.value * atr_entry
        return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=lev)
