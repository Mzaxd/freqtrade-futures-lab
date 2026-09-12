# Optimization experiment (iter-15): official-repo Supertrend + our regime
# adverse-veto overlay. Single change vs the upstream strategy: long entries are
# blocked while the regime detector says trend_down or turbulent; exits, stops,
# sizing and all other logic are untouched (upstream attribution: freqtrade/
# freqtrade-strategies repo, GPL-3.0, unmodified except noted here).
from pandas import DataFrame

from Supertrend import Supertrend as _Upstream

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from regime_loader import attach_regime  # noqa: E402


class SupertrendRegime(_Upstream):
    INTERFACE_VERSION = 3

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Upstream.populate_indicators(self, dataframe, metadata)
        dataframe = attach_regime(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Upstream.populate_entry_trend(self, dataframe, metadata)
        veto = dataframe["regime"].isin([1, 3])  # trend_down / turbulent
        for col in ("enter_long", "enter_short"):
            if col in dataframe.columns:
                dataframe.loc[veto, col] = 0
        return dataframe
