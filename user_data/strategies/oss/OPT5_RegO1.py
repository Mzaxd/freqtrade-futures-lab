# OPT5_RegO1 — Door-3 variant O1: no NEW entries while regime == 3 (turbulent).
#
# Both long and short entries are blocked; exits are untouched (entry gating
# only, mirroring the OPT4 atr08-gate pattern; OPT4's populate_exit_trend
# derives exits from raw signals, so blocking enter_* cannot affect exits).
# Regime attribution (Task A): turbulent bucket = 97 trades / +9.5k USDT /
# PF 1.26 / +98 per trade vs pool avg +345 — weakest efficiency, positive but
# thin. O1 tests whether skipping it improves DD enough to pay for the
# forgone profit.
from pandas import DataFrame

from OPT5_RegimeBase import OPT5_RegimeBase


class OPT5_RegO1(OPT5_RegimeBase):
    block_regimes = (3,)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        blocked = dataframe["regime"].isin(self.block_regimes) | (dataframe["regime"] < 0)
        dataframe.loc[blocked, "enter_long"] = 0
        dataframe.loc[blocked, "enter_short"] = 0
        return dataframe
