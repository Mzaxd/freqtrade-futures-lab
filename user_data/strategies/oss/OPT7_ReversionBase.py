"""OPT7_ReversionBase — Phase 7 / S2 (OversoldReversion deepening).

Inherits NC_OversoldReversion unchanged and exposes three pre-registered knobs:

  * DISLOCATION      — long-side dislocation threshold (parent default -0.30)
  * HOLD_HOURS       — time exit horizon (parent default 72)
  * SHORT_SIDE       — symmetric short entry: RSI(14) crosses ABOVE 70 AND price is
                       more than SHORT_DISLOCATION above the 50d SMA -> enter short;
                       exit is the same time-based rule (custom_exit is side-agnostic).

Long-side logic, liquidity machinery, MAX_POSITIONS=3 are inherited untouched.
Nothing else is altered — no stops, no ROI, no DCA beyond the parent's
liquidity-capped stake management (which is sizing, not martingale).

Pre-registered declaration set (phase7_s2):
  Stage 1 (D-grid, H72, long-only): D in {-0.20, -0.25, -0.30}
  Stage 2 (after D-grid): best-D x H96 ; best-D x H72 + short side on
  Selection rule for "best D": highest profit_abs among D-grid configs with
  >=30 trades and PF>=1.2; if none qualify, highest PF (failure noted).
"""
from __future__ import annotations

from pandas import DataFrame

from NC_OversoldReversion import NC_OversoldReversion


class OPT7_ReversionBase(NC_OversoldReversion):
    # knobs
    SHORT_SIDE = False
    RSI_THRESHOLD_SHORT = 70.0
    SHORT_DISLOCATION = 0.30   # price must be >30% above the 50d SMA (mirror)
    can_short = True           # enables enter_short; long-only subclasses never use it

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["rsi_cross_up"] = (
            (dataframe["rsi"] > self.RSI_THRESHOLD_SHORT)
            & (dataframe["rsi"].shift(1) <= self.RSI_THRESHOLD_SHORT)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        if self.SHORT_SIDE:
            dataframe.loc[
                dataframe["rsi_cross_up"]
                & (dataframe["dislocation"] > self.SHORT_DISLOCATION)
                & (dataframe["volume"] > 0),
                "enter_short",
            ] = 1
        return dataframe
