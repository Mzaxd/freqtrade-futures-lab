# Sub-strategy C: Bollinger z-score mean reversion, both directions, 1h.
# Native timeframe 1h; every trade must clear ~0.12% round-trip cost, hence
# entries require deep z extremes and a fast RSI(2) confirmation.
# Exits: revert to mid band, tight ATR stop, mid-band take-profit, time stop.
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    DecimalParameter,
    IntParameter,
    stoploss_from_absolute,
)

from regime_loader import attach_regime, risk_scale_for_regime


class MeanReversion(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 300

    order_types = {"entry": "market", "exit": "market", "stoploss": "market",
                   "stoploss_on_exchange": False}
    minimal_roi = {"0": 100.0}
    stoploss = -0.15  # catastrophe backstop (tight for MR)
    use_custom_stoploss = True
    position_adjustment_enable = False

    REGIME_GATED = False
    REGIME_STATE = 2  # range

    # ---------------- tunable parameters ----------------
    bb_period = 48                 # 2 days on 1h
    bb_std = DecimalParameter(2.0, 3.2, default=2.6, decimals=1, space="buy")
    rsi_len = 2
    rsi_lo = IntParameter(5, 15, default=10, space="buy")
    rsi_hi = IntParameter(85, 95, default=90, space="buy")
    atr_stop_mult = DecimalParameter(1.0, 3.0, default=1.6, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(0.8, 2.5, default=1.4, decimals=1, space="sell")
    base_risk = 0.005         # small size for MR (spec)
    leverage_fixed = 3
    time_stop_hours = 72      # 3 days max hold
    min_conf = 0.35
    # ------------------------------------------------------

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        mid = ta.SMA(dataframe, timeperiod=self.bb_period)
        std = dataframe["close"].rolling(self.bb_period).std()
        dataframe["bb_mid"] = mid
        dataframe["bb_z"] = (dataframe["close"] - mid) / std
        dataframe["rsi2"] = ta.RSI(dataframe, timeperiod=self.rsi_len)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        if self.REGIME_GATED:
            dataframe = attach_regime(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_ok = (
            (dataframe["bb_z"] <= -self.bb_std.value)
            & (dataframe["rsi2"] < self.rsi_lo.value)
            & (dataframe["volume"] > 0)
        )
        short_ok = (
            (dataframe["bb_z"] >= self.bb_std.value)
            & (dataframe["rsi2"] > self.rsi_hi.value)
            & (dataframe["volume"] > 0)
        )
        if self.REGIME_GATED:
            gate = (dataframe["regime"] == self.REGIME_STATE) & (dataframe["conf"] >= self.min_conf)
            long_ok &= gate
            short_ok &= gate
        dataframe.loc[long_ok, "enter_long"] = 1
        dataframe.loc[long_ok, "enter_tag"] = "meanrev"
        dataframe.loc[short_ok, "enter_short"] = 1
        dataframe.loc[short_ok, "enter_tag"] = "meanrev"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # take profit at mean reversion: close crosses the mid band
        dataframe.loc[
            (dataframe["close"] > dataframe["bb_mid"])
            & (dataframe["close"].shift(1) <= dataframe["bb_mid"].shift(1))
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        dataframe.loc[
            (dataframe["close"] < dataframe["bb_mid"])
            & (dataframe["close"].shift(1) >= dataframe["bb_mid"].shift(1))
            & (dataframe["volume"] > 0),
            "exit_short",
        ] = 1
        return dataframe

    # ------------------------------------------------------------------ plumbing
    def _signal_candle(self, pair: str, until: datetime):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(self.leverage_fixed, max_leverage)

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            stop_pct = max(float(self.atr_stop_mult.value) * float(row["atr"]) / float(row["close"]), 0.004)
            risk = self.base_risk
            if self.REGIME_GATED:
                conf = float(row.get("conf", 1.0) or 1.0)
                risk = risk_scale_for_regime(int(row.get("regime", -1)), conf, self.base_risk)
                if risk <= 0:
                    return 0.0
            equity = self.wallets.get_total_stake_amount()
            stake = equity * risk / stop_pct / max(leverage, 1.0)
            stake = min(stake, equity * 0.25, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit,
                        after_fill, **kwargs):
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            initial = trade.open_rate + self.atr_stop_mult.value * atr_entry
            extreme = trade.min_rate or trade.open_rate
            trail = extreme + self.atr_trail_mult.value * atr_entry
            return stoploss_from_absolute(min(initial, trail), current_rate,
                                          is_short=True, leverage=lev)
        initial = trade.open_rate - self.atr_stop_mult.value * atr_entry
        extreme = trade.max_rate or trade.open_rate
        trail = extreme - self.atr_trail_mult.value * atr_entry
        return stoploss_from_absolute(max(initial, trail), current_rate,
                                      is_short=False, leverage=lev)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if current_time - trade.open_date_utc > timedelta(hours=self.time_stop_hours):
            return "time_stop"
        return None
