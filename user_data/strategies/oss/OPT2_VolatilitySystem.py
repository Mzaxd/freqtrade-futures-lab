# OPT2_VolatilitySystem — Phase-2 variant of OPT1_VolatilitySystem (IS 2021-2022).
#
# Base = OPT1_VolatilitySystem with the phase-1 FROZEN parameters
#   signal_atr_mult=2.0 / resample_hours=3 / stop_atr_mult=2.0
# (IS: 139 trades / +424.22% / maxDD 11.92% / Sharpe 0.99 / PF 2.37 / funding -4,190).
# Those three parameters are frozen here (optimize=False) and stay OUT of the
# hyperopt spaces, so phase 2 measures only the marginal effect of the two
# additions below.
#
# Phase-2 additions (only these two):
#   1. ATR TRAILING STOP: custom_stoploss upgraded from "initial anchored stop"
#      to "initial anchored stop + trail from extreme after favorable move",
#      exactly the TrendBaselineV1 paradigm:
#        long:  stop = max(open − stop_mult×ATR_entry, max_rate − trail_mult×ATR_entry)
#        short: stop = min(open + stop_mult×ATR_entry, min_rate + trail_mult×ATR_entry)
#      via stoploss_from_absolute. New param atr_trail_mult (sell space).
#   2. BILATERAL FUNDING GATE: strictly causal `funding_rate` column via
#      opt_common.attach_funding (settlement series shifted one event, merged
#      as-of; NaN pairs = allowed).
#        enter_long &= funding_gate_long(df, funding_max)   (very positive funding blocks longs)
#        enter_short &= funding_gate_short(df, funding_max) (deeply negative funding blocks shorts)
#      New param funding_max (buy space).
#
# Everything else identical to OPT1: 1%-risk sizing (custom_stake_amount),
# no DCA, fixed 2x leverage, catastrophe cap stoploss=-0.30, ROI disabled.
#
# Hyperopt (IS only): SharpeHyperOptLoss, --spaces buy sell, --epochs 150,
# --random-state 42, -j 2, --timerange 20210101-20230101. No
# --analyze-per-epoch needed: neither hyperopt parameter is used inside
# populate_indicators (resample_hours is frozen at 3).
#
# Only IS window 20210101-20230101 was used for every run behind these defaults.
import sys
from datetime import datetime
from pathlib import Path

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

# Make the sibling opt_common module importable also inside hyperopt worker
# processes (loky spawns fresh interpreters that lack the strategy dir on
# sys.path, which would break cloudpickle's by-reference imports).
_STRAT_DIR = str(Path(__file__).resolve().parent)
if _STRAT_DIR not in sys.path:
    sys.path.insert(0, _STRAT_DIR)

import opt_common  # noqa: E402


class OPT2_VolatilitySystem(IStrategy):
    """
    Volatility breakout (frozen phase-1 signal) + ATR trailing stop +
    bilateral funding gate + 1%-risk sizing.
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

    # catastrophe backstop only; real stop is the ATR-anchored custom stop
    stoploss = -0.30
    use_custom_stoploss = True

    # no DCA / no position adding
    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # --- tunable parameters -----------------------------------------------------
    # FROZEN phase-1 parameters (optimize=False -> excluded from hyperopt):
    signal_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1,
                                       space="buy", optimize=False)
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1,
                                     space="sell", optimize=False)

    # NEW phase-2 parameters (the only hyperopt dimensions):
    # defaults = FROZEN phase-2 values (median of the 118 profitable epochs of
    # the 150-epoch IS hyperopt, SharpeHyperOptLoss, seed 42; funding median
    # 0.00125 snapped to the 0.0001 grid -> 0.0013. Plateau evidence: funding
    # dimension flat over 0.0012-0.0019; trail dimension monotone rising toward
    # the space edge (boundary effect - see report phase2_volatilitysystem.md).
    # Hyperopt sidecar json deleted; these .py defaults are authoritative.)
    # trailing stop distance in multiples of entry-time resampled ATR
    atr_trail_mult = DecimalParameter(1.0, 5.0, default=4.1, decimals=1, space="sell")
    # funding gate threshold (per-8h settled rate); high positive blocks longs,
    # deeply negative (|-threshold|) blocks shorts
    funding_max = DecimalParameter(0.0001, 0.0020, default=0.0013, decimals=4,
                                   space="buy")

    # risk model constants (fixed, not hyperopted) — identical to OPT1
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
        # raw ATR (NO multiplier) — used for signal threshold and stop distances
        resampled["atr"] = ta.ATR(resampled, timeperiod=14)
        resampled["close_change"] = resampled["close"].diff()
        resampled["abs_close_change"] = resampled["close_change"].abs()

        dataframe = resampled_merge(dataframe, resampled, fill_na=True)
        # column names embed the resample interval -> build them dynamically
        dataframe["atr_raw"] = dataframe[f"resample_{resample_int}_atr"]
        dataframe["close_change"] = dataframe[f"resample_{resample_int}_close_change"]
        dataframe["abs_close_change"] = dataframe[f"resample_{resample_int}_abs_close_change"]

        # phase-2 addition 2a: strictly causal settled funding rate column
        dataframe = opt_common.attach_funding(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        thr = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        long_cond = (
            (dataframe["close_change"] > thr)
            # phase-2 addition 2b: very positive settled funding blocks longs
            & opt_common.funding_gate_long(dataframe, self.funding_max.value)
        )
        short_cond = (
            (dataframe["close_change"] * -1 > thr)
            # phase-2 addition 2c: deeply negative settled funding blocks shorts
            & opt_common.funding_gate_short(dataframe, self.funding_max.value)
        )
        dataframe.loc[long_cond, "enter_long"] = 1
        dataframe.loc[short_cond, "enter_short"] = 1
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
        # risk-based sizing: notional * stop_pct = equity * risk_pct (as OPT1)
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
        # Initial stop anchored at the resampled ATR known at entry; after a
        # favorable move, trail from the extreme rate (TrendBaselineV1 paradigm).
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr_raw"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            initial_stop = trade.open_rate + self.stop_atr_mult.value * atr_entry
            extreme = trade.min_rate or trade.open_rate
            trail_stop = extreme + self.atr_trail_mult.value * atr_entry
            stop_price = min(initial_stop, trail_stop)
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=lev)
        initial_stop = trade.open_rate - self.stop_atr_mult.value * atr_entry
        extreme = trade.max_rate or trade.open_rate
        trail_stop = extreme - self.atr_trail_mult.value * atr_entry
        stop_price = max(initial_stop, trail_stop)
        return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=lev)
