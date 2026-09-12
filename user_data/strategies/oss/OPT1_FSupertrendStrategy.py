"""
OPT1 — Phase-1 optimized variant of FSupertrendStrategy (futures lab).

Baseline (FSupertrendStrategy, IS 2021-01-01..2023-01-01, 1h, BTC/ETH/SOL,
fee 0.05%/side): 1026 trades, all long, +63.75%, maxDD 23.92%, Sharpe 0.86,
PF 1.08, avg profit/trade 0.18%, funding -2304 USDT, avg duration 14.6h.

Changes vs the original (ONLY these three):
  1. can_short = True
     The original file already contains complete enter_short/exit_short logic
     (enter_short when all 3 sell supertrends are 'down'; exit_short when the
     buy_m2 supertrend turns 'up') but never declared can_short, so in futures
     mode the short side never fired.  Activating it unchanged.
  2. Funding gate on the LONG side only (phase-1 spec):
     populate_indicators attaches a strictly causal `funding_rate` column via
     opt_common.attach_funding; long entries additionally require
     opt_common.funding_gate_long(df, funding_max) (True = allowed; pairs
     without funding data are always allowed).  Short side left ungated.
  3. minimal_roi retuned by hyperopt (spaces: buy roi) on the IS window.
     The original {"0":0.1,"30":0.75,"60":0.05,"120":0.025} table is a
     hyperopt artifact (75% at 30min virtually never triggers).

Deliberately UNTOUCHED: stoploss (-0.265), trailing stop (0.05/0.10), and the
six supertrend m/p parameter groups (kept at the original hyperopt values,
marked optimize=False so they stay out of the hyperopt search space).
"""

import logging
import sys
from pathlib import Path

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame
import pandas as pd

import technical.indicators as ftt

# Make the sibling opt_common module importable also inside hyperopt worker
# processes (loky spawns fresh interpreters that lack the strategy dir on
# sys.path, which would break cloudpickle's by-reference imports).
_STRAT_DIR = str(Path(__file__).resolve().parent)
if _STRAT_DIR not in sys.path:
    sys.path.insert(0, _STRAT_DIR)

import opt_common  # noqa: E402

logger = logging.getLogger(__name__)


class OPT1_FSupertrendStrategy(IStrategy):
    INTERFACE_VERSION: int = 3

    can_short = True

    # Buy params: supertrend values are the ORIGINAL hyperopt results, frozen
    # (optimize=False below). funding_max is the phase-1 funding gate
    # (hyperopt epoch 127/150 backfilled).
    buy_params = {
        "buy_m1": 4,
        "buy_m2": 7,
        "buy_m3": 1,
        "buy_p1": 8,
        "buy_p2": 9,
        "buy_p3": 8,
        "funding_max": 0.0011,
    }

    # Sell params: original values, untouched.
    sell_params = {
        "sell_m1": 1,
        "sell_m2": 3,
        "sell_m3": 6,
        "sell_p1": 16,
        "sell_p2": 18,
        "sell_p3": 18,
    }

    # ROI table: hyperopt epoch 127/150 (SharpeHyperOptLoss, spaces buy+roi,
    # IS 20210101-20230101, rs=42). Original artifact table replaced.
    minimal_roi = {"0": 0.165, "202": 0.072, "776": 0.028, "1438": 0}

    # Stoploss: untouched.
    stoploss = -0.265

    # Trailing stop: untouched.
    trailing_stop = True
    trailing_stop_positive = 0.05
    trailing_stop_positive_offset = 0.1
    trailing_only_offset_is_reached = False

    timeframe = "1h"

    startup_candle_count = 18

    # Funding gate threshold (per-8h settled rate), hyperopt epoch 127 value.
    funding_max = DecimalParameter(
        0.0001, 0.0020, default=0.0011, decimals=4, space="buy"
    )

    # Supertrend parameter groups: original values, excluded from hyperopt.
    buy_m1 = IntParameter(1, 7, default=4, optimize=False)
    buy_m2 = IntParameter(1, 7, default=7, optimize=False)
    buy_m3 = IntParameter(1, 7, default=1, optimize=False)
    buy_p1 = IntParameter(7, 21, default=8, optimize=False)
    buy_p2 = IntParameter(7, 21, default=9, optimize=False)
    buy_p3 = IntParameter(7, 21, default=8, optimize=False)

    sell_m1 = IntParameter(1, 7, default=1, optimize=False)
    sell_m2 = IntParameter(1, 7, default=3, optimize=False)
    sell_m3 = IntParameter(1, 7, default=6, optimize=False)
    sell_p1 = IntParameter(7, 21, default=16, optimize=False)
    sell_p2 = IntParameter(7, 21, default=18, optimize=False)
    sell_p3 = IntParameter(7, 21, default=18, optimize=False)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        new_cols = []

        for multiplier in self.buy_m1.range:
            for period in self.buy_p1.range:
                new_cols.append(
                    self.supertrend_direction(
                        dataframe,
                        multiplier,
                        period,
                        f"supertrend_1_buy_{multiplier}_{period}",
                    )
                )

        for multiplier in self.buy_m2.range:
            for period in self.buy_p2.range:
                new_cols.append(
                    self.supertrend_direction(
                        dataframe,
                        multiplier,
                        period,
                        f"supertrend_2_buy_{multiplier}_{period}",
                    )
                )

        for multiplier in self.buy_m3.range:
            for period in self.buy_p3.range:
                new_cols.append(
                    self.supertrend_direction(
                        dataframe,
                        multiplier,
                        period,
                        f"supertrend_3_buy_{multiplier}_{period}",
                    )
                )

        for multiplier in self.sell_m1.range:
            for period in self.sell_p1.range:
                new_cols.append(
                    self.supertrend_direction(
                        dataframe,
                        multiplier,
                        period,
                        f"supertrend_1_sell_{multiplier}_{period}",
                    )
                )

        for multiplier in self.sell_m2.range:
            for period in self.sell_p2.range:
                new_cols.append(
                    self.supertrend_direction(
                        dataframe,
                        multiplier,
                        period,
                        f"supertrend_2_sell_{multiplier}_{period}",
                    )
                )

        for multiplier in self.sell_m3.range:
            for period in self.sell_p3.range:
                new_cols.append(
                    self.supertrend_direction(
                        dataframe,
                        multiplier,
                        period,
                        f"supertrend_3_sell_{multiplier}_{period}",
                    )
                )

        if new_cols:
            dataframe = pd.concat([dataframe] + new_cols, axis=1)

        # Causal funding rate column for the long-side gate (phase-1 addition).
        dataframe = opt_common.attach_funding(dataframe, metadata["pair"])

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        dataframe.loc[
            (
                dataframe[f"supertrend_1_buy_{self.buy_m1.value}_{self.buy_p1.value}"]
                == "up"
            )
            & (
                dataframe[f"supertrend_2_buy_{self.buy_m2.value}_{self.buy_p2.value}"]
                == "up"
            )
            & (
                dataframe[f"supertrend_3_buy_{self.buy_m3.value}_{self.buy_p3.value}"]
                == "up"
            )
            & (  # The three indicators are 'up' for the current candle
                dataframe["volume"] > 0
            )
            & (  # Phase-1 funding gate: block longs when settled funding is hot
                opt_common.funding_gate_long(dataframe, self.funding_max.value)
            ),
            "enter_long",
        ] = 1

        dataframe.loc[
            (
                dataframe[
                    f"supertrend_1_sell_{self.sell_m1.value}_{self.sell_p1.value}"
                ]
                == "down"
            )
            & (
                dataframe[
                    f"supertrend_2_sell_{self.sell_m2.value}_{self.sell_p2.value}"
                ]
                == "down"
            )
            & (
                dataframe[
                    f"supertrend_3_sell_{self.sell_m3.value}_{self.sell_p3.value}"
                ]
                == "down"
            )
            & (  # The three indicators are 'down' for the current candle
                dataframe["volume"] > 0
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                dataframe[
                    f"supertrend_2_sell_{self.sell_m2.value}_{self.sell_p2.value}"
                ]
                == "down"
            ),
            "exit_long",
        ] = 1

        dataframe.loc[
            (
                dataframe[f"supertrend_2_buy_{self.buy_m2.value}_{self.buy_p2.value}"]
                == "up"
            ),
            "exit_short",
        ] = 1

        return dataframe

    def supertrend_direction(
        self, dataframe: DataFrame, multiplier: int, period: int, name: str
    ) -> pd.Series:
        """
        Supertrend direction ('up' / 'down') as a named series.
        `ftt.supertrend` returns a (value, direction) tuple - only the direction is used here.
        """
        _, stx = ftt.supertrend(dataframe, period=period, multiplier=multiplier)
        # 'stx' is None before the indicator has warmed up - keep the empty string
        return pd.Series(stx, index=dataframe.index, name=name).fillna("")
