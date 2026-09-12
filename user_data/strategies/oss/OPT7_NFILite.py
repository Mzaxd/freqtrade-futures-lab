# OPT7_NFILite — Phase 7 S1: extracted NFI entry families with a clean exit
# discipline. Long-only by default (short family set is empty unless edited).
#
# Design (see research_openstrat/reports/phase7_s1_nfi.md):
#   ENTRY: reuse the unmodified NostalgiaForInfinityX7 signal engine (all
#   indicators + multi-TF protections inherited), then keep only candles whose
#   enter_tag contains one of NFLITE_LONG_FAMILIES (X7 records family ids in
#   enter_tag, e.g. "141 142 "). Families that require DCA to work (grind 120,
#   rebuy 61-65) are excluded — the lab forbids position adjustment.
#   EXIT (simple discipline, replaces X7's 100%-custom_exit machinery):
#     1. take profit on overbought: 5m RSI_3 >= tp_rsi_long (X7's own exits
#        are RSI-ladder based, so RSI_3 is the native profit gauge of these
#        dip-buying families) — populate_exit_trend, evaluated on candle close.
#     2. ATR stop (initial, non-trailing): stop_atr_mult * ATR(14) on 1h
#        resample, anchored at the entry signal candle (OPT1_VolatilitySystem
#        pattern via stoploss_from_absolute). Rationale: entries are capitulation
#        dips; the stop must sit beyond 1h-scale noise (14 h of typical range).
#     3. time stop: exit after max_hold_h hours (X7's median hold is ~1-3 h;
#        48 h bounds the tail without cutting the body).
#     4. catastrophe cap stoploss=-0.15 (price, 1x leverage) — backstop only.
#   confirm_trade_exit is overridden to always allow exits: X7's inherited
#   version CANCELS non-liquidation stop_loss exits (it expects DCA to rescue),
#   which would silently disable the ATR stop.
#   SIZING: 1% equity risk per trade (OPT1 pattern): stop_pct = stop distance /
#   entry price (floor 0.5%), notional = equity * 0.01 / stop_pct, margin capped
#   at 35% of equity, leverage 1x. position_adjustment_enable = False.
#
# No lookahead: entries/exits use inherited X7 signals on closed candles; ATR and
# RSI values are taken from the last closed candle; sizing reads the signal
# candle (entry happens on the next candle open, same as freqtrade semantics).
import os
from datetime import datetime

import pandas as pd
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

from technical.util import resample_to_interval, resampled_merge

try:
    from NostalgiaForInfinityX7 import NostalgiaForInfinityX7
except ImportError:
    from user_data.strategies.oss.NostalgiaForInfinityX7 import NostalgiaForInfinityX7


def _fam_set(env: str, default: str) -> frozenset:
    raw = os.environ.get(env, default)
    return frozenset(t.strip() for t in raw.replace(";", ",").split(",") if t.strip())


class OPT7_NFILite(NostalgiaForInfinityX7):
    """NFI entry families (top_coins dips) + ATR stop / RSI TP / time stop."""

    INTERFACE_VERSION = 3

    # --- lab rules -----------------------------------------------------------
    position_adjustment_enable = False
    max_entry_position_adjustment = 0
    use_custom_stoploss = True
    # catastrophe backstop (price distance, 1x)
    stoploss = -0.15
    # ROI exits off
    minimal_roi = {"0": 100}

    # --- entry family selection (env-overridable; defaults frozen after IS) ---
    NFLITE_LONG_FAMILIES = _fam_set("OPT7_NFLITE_LONG", "141,142,143")
    NFLITE_SHORT_FAMILIES = _fam_set("OPT7_NFLITE_SHORT", "")

    # own copies of the enable dicts (families not selected are still computed
    # by X7 but filtered out below; keeping computation identical avoids any
    # re-indexing side effects and costs nothing measurable)
    long_entry_signal_params = dict(NostalgiaForInfinityX7.long_entry_signal_params)
    short_entry_signal_params = dict(NostalgiaForInfinityX7.short_entry_signal_params)

    # --- exit parameters (frozen defaults; rationale in header) ---------------
    # MAE evidence (opt7_probe_base_12p_is, families 141-145): median adverse
    # excursion ~2%, p90 ~8.5%, worst (non-flash-crash) ~13%. ATR(1h) at entry
    # is already inflated by the capitulation candle, so 3x ATR(14) sits beyond
    # the p90 excursion in crash conditions -> stop_atr_mult = 3.0.
    tp_rsi_long = float(os.environ.get("OPT7_TP_RSI", 75.0))   # 5m RSI_3 overbought -> TP
    tp_rsi_short = 25.0
    stop_atr_mult = float(os.environ.get("OPT7_STOP_MULT", 3.0))  # stop = mult * 1h ATR(14)
    stop_pct_floor = 0.005    # min stop distance 0.5% (sizing floor)
    max_hold_h = float(os.environ.get("OPT7_MAXH", 48.0))      # time stop
    # --- sizing ---------------------------------------------------------------
    risk_pct = 0.01           # equity risk per trade
    margin_cap = 0.35         # max margin per trade as fraction of equity

    # ------------------------------------------------------------------ setup
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return 1.0

    # ------------------------------------------------------------- indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        # own ATR on 1h resample (X7 stores no plain ATR column)
        resampled = resample_to_interval(dataframe, 60)
        from talib import abstract as ta
        resampled["nfl_atr"] = ta.ATR(resampled, timeperiod=14)
        dataframe = resampled_merge(dataframe, resampled, fill_na=True)
        dataframe["nfl_atr"] = dataframe["resample_60_nfl_atr"]
        return dataframe

    # ----------------------------------------------------------------- entry
    @staticmethod
    def _tag_mask(df: DataFrame, families: frozenset) -> pd.Series:
        if not families:
            return pd.Series(False, index=df.index)
        padded = " " + df["enter_tag"].fillna("") + " "
        mask = None
        for f in families:
            m = padded.str.contains(f" {f} ", regex=False)
            mask = m if mask is None else (mask | m)
        return mask.fillna(False)

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_entry_trend(df, metadata)
        keep_long = self._tag_mask(df, self.NFLITE_LONG_FAMILIES)
        keep_short = self._tag_mask(df, self.NFLITE_SHORT_FAMILIES)
        df.loc[~keep_long, "enter_long"] = 0
        df.loc[~keep_short, "enter_short"] = 0
        return df

    # ------------------------------------------------------------------ exit
    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[:, "exit_long"] = 0
        df.loc[:, "exit_short"] = 0
        # 1. take profit on overbought/oversold (5m RSI_3, candle close)
        df.loc[df["RSI_3"] >= self.tp_rsi_long, "exit_long"] = 1
        if self.can_short:
            df.loc[df["RSI_3"] <= self.tp_rsi_short, "exit_short"] = 1
        return df

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # 3. time stop
        age_h = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_h >= self.max_hold_h:
            return "nfl_time_stop"
        return None

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs):
        # 2. initial ATR stop anchored at entry (no trailing)
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            idx = df["date"].searchsorted(trade.open_date_utc) - 1
            atr = float(df.iloc[idx]["nfl_atr"])
        except Exception:
            return None
        if not atr or atr <= 0 or idx < 0:
            return None
        if trade.is_short:
            stop_price = trade.open_rate + self.stop_atr_mult * atr
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=1.0)
        stop_price = trade.open_rate - self.stop_atr_mult * atr
        return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=1.0)

    # X7 cancels non-liquidation stop-loss exits (expects DCA to rescue);
    # without DCA that would disable the ATR stop -> always allow.
    def confirm_trade_exit(self, pair, trade, order_type, amount, rate,
                           time_in_force, exit_reason, current_time, **kwargs) -> bool:
        return True

    # --------------------------------------------------------------- sizing
    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake, max_stake: float, leverage: float,
                            entry_tag, side: str, **kwargs) -> float:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            idx = df["date"].searchsorted(current_time) - 1
            row = df.iloc[idx]
            atr = float(row["nfl_atr"])
            close = float(row["close"])
            if not atr or atr <= 0 or not close or close <= 0:
                return proposed_stake
            stop_pct = max(self.stop_atr_mult * atr / close, self.stop_pct_floor)
            equity = self.wallets.get_total_stake_amount()
            stake = equity * self.risk_pct / stop_pct
            stake = min(stake, equity * self.margin_cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake
