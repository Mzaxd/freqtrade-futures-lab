"""Merge candidate C1: G pre-registered winner params 1.9/3.0 x atr08 gate x ts60 (MOT6 via CLI)."""
from freqtrade.strategy import DecimalParameter
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT4_C1(OPT4_VolatilitySystem):
    signal_atr_mult = DecimalParameter(1.0, 4.0, default=1.9, decimals=1, space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.0, 4.0, default=3.0, decimals=1, space="sell", optimize=False)
