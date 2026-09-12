# OPT4_Struct_gate — Phase-4 structure experiments (Agent-H): regime gates on NEW entries only.
#
# Frozen OPT1 parameters: signal_atr_mult=2.0, resample_hours=3, stop_atr_mult=2.0
# (NOT tuned here; agent G owns the parameter search — orthogonal).
#
# Gate modes (chosen via class attribute `gate_mode`, set by subclasses in OPT4_Struct_variants.py):
#   "adx"      : 1h ADX(14) >= adx_threshold on the signal row -> new entries allowed
#                (long and short share the same gate). Thresholds 15 / 20 / 25.
#   "atr_pct"  : resampled ATR (atr_raw) >= atr_gate_mult * rolling 30-day median of atr_raw.
#                Window = 720 closed 1h candles ending at the signal row, min_periods=168
#                (with startup_candle_count=200 the median exists from the first backtest
#                candle, so no extra warmup loss). Strictly backward-looking -> causal.
#                Coefficients 0.8 / 1.0.
#   "cooldown" : after a stoploss exit on a pair, block NEW entries on that pair for
#                cooldown_hours (48 / 96). Implemented in confirm_trade_entry via
#                Trade.get_trades_proxy (supported in backtest mode per freqtrade docs);
#                exits are untouched.
#
# Exits are IDENTICAL to OPT1: exit columns derive from the RAW (ungated) signals, so a gate
# never delays or cancels a reverse-signal exit or the ATR stop. Only enter_* columns are gated.
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade

from OPT1_VolatilitySystem import OPT1_VolatilitySystem


class OPT4_Struct_gate(OPT1_VolatilitySystem):
    gate_mode: str | None = None     # None | "adx" | "atr_pct" | "cooldown"
    adx_threshold = 20.0
    atr_gate_mult = 1.0
    atr_gate_window = 30 * 24        # 30d rolling median of resampled ATR (on 1h rows)
    atr_gate_min_periods = 7 * 24    # available after 7d of history (startup=200h covers it)
    cooldown_hours = 48

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        if self.gate_mode == "adx":
            dataframe["gate_adx"] = ta.ADX(dataframe, timeperiod=14)
        elif self.gate_mode == "atr_pct":
            dataframe["gate_atr_med"] = (
                dataframe["atr_raw"]
                .rolling(self.atr_gate_window, min_periods=self.atr_gate_min_periods)
                .median()
            )
        return dataframe

    def _entry_gate_mask(self, dataframe: DataFrame):
        """Boolean mask: True = new entries allowed on this row. NaN compares False (blocked)."""
        if self.gate_mode == "adx":
            return dataframe["gate_adx"] >= self.adx_threshold
        if self.gate_mode == "atr_pct":
            return dataframe["atr_raw"] >= self.atr_gate_mult * dataframe["gate_atr_med"]
        return None

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        thr = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        long_sig = dataframe["close_change"] > thr
        short_sig = dataframe["close_change"] * -1 > thr
        if self.gate_mode in ("adx", "atr_pct"):
            gate = self._entry_gate_mask(dataframe).fillna(False)
            long_sig = long_sig & gate
            short_sig = short_sig & gate
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe.loc[long_sig, "enter_long"] = 1
        dataframe.loc[short_sig, "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # identical to OPT1: exits derive from the RAW signals, never from the gate
        thr = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        long_sig = dataframe["close_change"] > thr
        short_sig = dataframe["close_change"] * -1 > thr
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        dataframe.loc[short_sig, "exit_long"] = 1
        dataframe.loc[long_sig, "exit_short"] = 1
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        # cooldown gate: block re-entry on a pair within cooldown_hours after a stoploss exit
        if self.gate_mode == "cooldown" and self.cooldown_hours > 0:
            closed = Trade.get_trades_proxy(pair=pair, is_open=False)
            if closed:
                last = max(closed, key=lambda t: t.close_date_utc)
                if (last.exit_reason in ("stop_loss", "liquidation")
                        and last.close_date_utc is not None
                        and current_time < last.close_date_utc + timedelta(hours=self.cooldown_hours)):
                    return False
        return True
