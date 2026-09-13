"""Phase-7 experiment: OPT4 with base timeframe 15m (signal resample stays 3h).
Gate median recomputed with a TIME-based 30d window (atr_raw is 3h-resampled and
ffilled, so row-count windows at 15m would need >5x Binance fetch limit)."""
import pandas as pd
from pandas import DataFrame
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT7_VolSys15m(OPT4_VolatilitySystem):
    timeframe = "15m"
    startup_candle_count = 700   # ~7d at 15m; gate min-period is 7d (NaN -> open) before that

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        # replace the row-count gate median with a time-based one
        s = dataframe.set_index("date")["atr_raw"]
        med = s.rolling("30D", min_periods=672).median()
        dataframe["gate_atr_med"] = med.to_numpy()
        return dataframe
