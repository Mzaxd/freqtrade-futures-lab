from pandas import DataFrame
from OPT9_VolatilitySystem import OPT9_VolatilitySystem as _Base


class Stress_OPT9_delay1(_Base):
    """Entry delayed by 1 candle (stress: latency). Same template as the
    phase-3 vetting delay variants (enter columns shifted; exits untouched)."""

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Base.populate_entry_trend(self, dataframe, metadata)
        for col in ("enter_long", "enter_short"):
            if col in dataframe.columns:
                dataframe[col] = dataframe[col].shift(1).fillna(0.0)
        return dataframe
