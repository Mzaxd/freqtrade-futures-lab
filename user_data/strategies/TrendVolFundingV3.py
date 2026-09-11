# Strategy v3 - Trend following (same core as v1) + volatility regime filter
#               + funding-rate crowding filter. Long & short, futures isolated, 1h.
#
# Single hypothesis delta vs v1: entries are additionally filtered by
#   (a) volatility regime: ATR/close percentile rank over the last vol_lookback hours
#       must lie within [vol_pct_min, vol_pct_max] (skip dead chop and panic spikes);
#   (b) funding crowding: skip longs when 8h funding > +funding_max_abs (longs pay
#       dearly / crowded longs), skip shorts when funding < -funding_max_abs.
# Exits identical to v1 (trend-break signal, ATR initial + trailing stop, time stop).
# Sizing identical to v1 (risk ~1% equity, 3x leverage). No martingale / adding / grid.
from datetime import datetime, timedelta

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    stoploss_from_absolute,
)


class TrendVolFundingV3(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True

    # EMA200 (200) + 720h percentile window -> need ~1000 candles.
    startup_candle_count: int = 999

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    minimal_roi = {"0": 100.0}
    stoploss = -0.30
    use_custom_stoploss = True
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # ======================= tunable parameters =======================
    ema_fast = 20
    ema_slow = 50
    ema_trend = 200
    # defaults = IS plateau medians (hyperopt round3, 250 epochs, SharpeHyperOptLoss, seed=42;
    # 216/250 epochs profitable; see reports/plateau_TrendVolFundingV3b.md)
    adx_min = IntParameter(15, 30, default=16, space="buy")
    atr_period = 14
    atr_stop_mult = DecimalParameter(2.0, 4.0, default=2.1, decimals=1, space="sell")
    atr_trail_mult = DecimalParameter(1.0, 5.0, default=3.8, decimals=1, space="sell")
    # volatility regime filter
    vol_lookback = 720  # hours (30 days)
    vol_min_periods = 200
    vol_pct_min = DecimalParameter(0.05, 0.35, default=0.15, decimals=2, space="buy")
    vol_pct_max = DecimalParameter(0.70, 0.98, default=0.91, decimals=2, space="buy")
    # funding crowding filter (per 8h interval; typical neutral = 0.0001 = 0.01%)
    funding_max_abs = DecimalParameter(0.0001, 0.0006, default=0.0003, decimals=4, space="buy")
    risk_pct = 0.01
    leverage_fixed = 3
    time_stop_hours = 24 * 28
    # ===================================================================

    def informative_pairs(self):
        # funding rate series for the whitelist pairs (needed in dry-run/live;
        # in backtest the data is read from disk directly).
        pairs = self.dp.current_whitelist() if self.dp else []
        return [(p, "8h", "funding_rate") for p in pairs]

    @staticmethod
    def _merge_funding(dataframe: DataFrame, funding: DataFrame) -> DataFrame:
        """Attach the most recent *past* funding rate to every candle (merge_asof
        backward: funding event at time T is visible to candles dated >= T)."""
        fund = funding[["date", "funding_rate"]].rename(columns={"funding_rate": "funding_rate_8h"})
        fund = fund.dropna().sort_values("date")
        dataframe = pd.merge_asof(
            dataframe.sort_values("date"), fund, on="date", direction="backward"
        )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)

        # volatility percentile over trailing window (inclusive of current closed candle)
        atr_pct = dataframe["atr"] / dataframe["close"]
        dataframe["atr_pct_rank"] = atr_pct.rolling(self.vol_lookback, min_periods=self.vol_min_periods).rank(pct=True)

        # funding rate: most recent past 8h rate attached to each candle
        try:
            funding = self.dp.get_pair_dataframe(metadata["pair"], "8h", candle_type="funding_rate")
            dataframe = self._merge_funding(dataframe, funding)
        except Exception:
            dataframe["funding_rate_8h"] = 0.0
        if "funding_rate_8h" not in dataframe.columns:
            dataframe["funding_rate_8h"] = 0.0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        vol_ok = (
            (dataframe["atr_pct_rank"] > self.vol_pct_min.value)
            & (dataframe["atr_pct_rank"] < self.vol_pct_max.value)
        )
        fund_ok_long = dataframe["funding_rate_8h"] < self.funding_max_abs.value
        fund_ok_short = dataframe["funding_rate_8h"] > -self.funding_max_abs.value

        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["adx"] > self.adx_min.value)
                & vol_ok
                & fund_ok_long
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["close"] < dataframe["ema_trend"])
                & (dataframe["adx"] > self.adx_min.value)
                & vol_ok
                & fund_ok_short
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
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
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        return dataframe

    # ------------------------------------------------------------------ helpers
    def _signal_candle(self, pair: str, until: datetime):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return min(self.leverage_fixed, max_leverage)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            stop_pct = float(self.atr_stop_mult.value) * float(row["atr"]) / float(row["close"])
            stop_pct = max(stop_pct, 0.005)
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = notional / max(leverage, 1.0)
            stake = min(stake, equity * 0.35, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            initial_stop = trade.open_rate + self.atr_stop_mult.value * atr_entry
            extreme = trade.min_rate or trade.open_rate
            trail_stop = extreme + self.atr_trail_mult.value * atr_entry
            return stoploss_from_absolute(min(initial_stop, trail_stop), current_rate, is_short=True, leverage=lev)
        else:
            initial_stop = trade.open_rate - self.atr_stop_mult.value * atr_entry
            extreme = trade.max_rate or trade.open_rate
            trail_stop = extreme - self.atr_trail_mult.value * atr_entry
            return stoploss_from_absolute(max(initial_stop, trail_stop), current_rate, is_short=False, leverage=lev)

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        if current_time - trade.open_date_utc > timedelta(hours=self.time_stop_hours):
            return "time_stop"
        return None
