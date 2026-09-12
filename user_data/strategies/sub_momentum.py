# Sub-strategy A: 4h EMA-cross trend momentum, long-only (for trend_up regimes).
#
# History: the original Donchian-breakout engine (this file, v1) was eliminated
# on evidence twice - prior round hyperopt (no profitable region on 4h) and
# iter-4 routed IS (-1835 USDT gated). Replaced in iter-6 by the EMA-cross
# momentum engine, the only long engine with proven IS edge in this lab
# (prior round TrendBaselineV1b IS +52% both-side; long side isolated here).
#
# Routed mode (REGIME_GATED=True) enters only while regime==trend_up and scales
# risk by regime confidence; standalone mode (REGIME_GATED=False) is used for
# the routing-gain comparison. Exits: EMA cross-back signal, ATR initial stop,
# ATR trailing stop, time stop. No martingale / no adding / stop always present.
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    stoploss_from_absolute,
)

from regime_loader import attach_regime, risk_scale_for_regime


class TrendLong(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 400

    order_types = {"entry": "market", "exit": "market", "stoploss": "market",
                   "stoploss_on_exchange": False}
    minimal_roi = {"0": 100.0}
    stoploss = -0.30  # catastrophe backstop
    use_custom_stoploss = True
    position_adjustment_enable = False

    REGIME_GATED = False
    REGIME_STATE = 0  # trend_up

    # ---------------- tunable parameters ----------------
    ema_fast = 20
    ema_slow = 50
    ema_trend = 200
    adx_min = IntParameter(15, 30, default=18, space="buy")
    atr_stop_mult = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.0, 5.0, default=4.2, decimals=1, space="sell")
    base_risk = 0.010          # 1.0% equity risk per trade (routed: x conf)
    leverage_fixed = 3
    time_stop_hours = 24 * 28
    min_conf = 0.35
    # ------------------------------------------------------

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        if self.REGIME_GATED:
            dataframe = attach_regime(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # state-continuous setup: entry whenever the trend setup holds (freqtrade
        # enters once, when no position is open) - NOT only at the cross event,
        # whose coincidence with a regime window starved the sample (iter-4/5).
        ok = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["adx"] > self.adx_min.value)
            & (dataframe["volume"] > 0)
        )
        if self.REGIME_GATED:
            ok &= (dataframe["regime"] == self.REGIME_STATE) & (dataframe["conf"] >= self.min_conf)
        dataframe.loc[ok, "enter_long"] = 1
        dataframe.loc[ok, "enter_tag"] = "trendlong"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
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
            stop_pct = max(float(self.atr_stop_mult.value) * float(row["atr"]) / float(row["close"]), 0.005)
            risk = self.base_risk
            if self.REGIME_GATED:
                conf = float(row.get("conf", 1.0) or 1.0)
                risk = risk_scale_for_regime(int(row.get("regime", -1)), conf, self.base_risk)
                if risk <= 0:
                    return 0.0
            equity = self.wallets.get_total_stake_amount()
            stake = equity * risk / stop_pct / max(leverage, 1.0)
            stake = min(stake, equity * 0.35, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair, trade: Trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        lev = trade.leverage or 1.0
        initial = trade.open_rate - self.atr_stop_mult.value * atr_entry
        extreme = trade.max_rate or trade.open_rate
        trail = extreme - self.atr_trail_mult.value * atr_entry
        return stoploss_from_absolute(max(initial, trail), current_rate,
                                      is_short=False, leverage=lev)

    def custom_exit(self, pair, trade: Trade, current_time, current_rate,
                    current_profit, **kwargs):
        if current_time - trade.open_date_utc > timedelta(hours=self.time_stop_hours):
            return "time_stop"
        return None
