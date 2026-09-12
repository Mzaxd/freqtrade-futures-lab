# OPT4_VolatilitySystem — Phase-4 deep-optimized VolatilitySystem (G×H merge).
#
# Composition (all components validated independently within 20210101-20240101,
# see research_openstrat/reports/phase4_{charter,paramtune,structure}.md):
#   * OPT1 risk structure (unchanged): ATR-anchored initial stop, 1%-equity risk
#     sizing, no DCA, 2x leverage, catastrophe cap -0.30.
#   * atr08 entry gate (Agent-H winner): new entries (both sides) only when the
#     resampled ATR >= 0.8x its own 30-day rolling median — blocks low-volatility
#     fakeout breakouts. Exits always derive from the RAW signals (never gated).
#   * 60-day time stop (weak-adopt, hygiene against zombie positions).
#   * signal_atr_mult / stop_atr_mult defaults = merge-comparison winner C2
#     (2.0/2.0 — the ORIGINAL VolatilitySystem signal values, zero tuning
#     degrees: the parameter surface is a profit/DD dial and the dial was
#     left at factory settings; G's pre-registered 1.9/3.0 and midpoint
#     2.0/3.0 lost the MOT-reconciled merge comparison).
#   * Deployment: 12-coin universe, max_open_trades 4 (MOT5+ breaks the 20% DD
#     bar via concurrent stop-clusters; MOT4 = max Sharpe AND min DD among
#     qualifiers). Set via config (--max-open-trades 4).
#
# FROZEN 2026-09-12 after phase-4 vetting: 12-coin IS-pool +1495.8% / DD 15.92%
# / Sharpe 1.01 / PF 1.97; six half-year slices all positive (worst +10.5%);
# fee x3 -> +1216%; delay-1 retention 86%; lookahead clean. Disclosed regression
# on the burned 2024-26 window: +102.6% / DD 42.3% (12p), +89.6% / DD 31.2%
# (3p) — the 2026H1-type high-vol chop regime remains the known weakness.
from datetime import datetime, timedelta

from pandas import DataFrame

from freqtrade.persistence import Trade

from OPT1_VolatilitySystem import OPT1_VolatilitySystem


class OPT4_VolatilitySystem(OPT1_VolatilitySystem):
    # --- phase-4 knobs (defaults finalized by the C1/C2/C3 merge comparison) ---
    # signal_atr_mult / stop_atr_mult are inherited DecimalParameters; subclasses
    # of this file pin their defaults per candidate. After selection the winner's
    # values are re-declared here (optimize=False, frozen for dry-run).
    gate_atr_mult = 0.8            # atr08: entries need ATR >= 0.8 x 30d median
    gate_atr_window = 30 * 24      # 30d rolling median of resampled ATR (1h rows)
    gate_atr_min_periods = 7 * 24
    time_stop_days = 60

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["gate_atr_med"] = (
            dataframe["atr_raw"]
            .rolling(self.gate_atr_window, min_periods=self.gate_atr_min_periods)
            .median()
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # raw signals first (identical to OPT1) ...
        thr = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        long_sig = dataframe["close_change"] > thr
        short_sig = dataframe["close_change"] * -1 > thr
        # ... then the atr08 gate on NEW entries only (NaN median -> blocked)
        gate = (dataframe["atr_raw"] >= self.gate_atr_mult * dataframe["gate_atr_med"]).fillna(False)
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe.loc[long_sig & gate, "enter_long"] = 1
        dataframe.loc[short_sig & gate, "enter_short"] = 1
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

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        if (current_time - trade.open_date_utc).days >= self.time_stop_days:
            return "time_stop_60d"
        return None
