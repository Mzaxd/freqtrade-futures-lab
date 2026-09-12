"""Merge candidate C3: G-suggested midpoint 2.0/3.0 x atr08 gate x ts60 (MOT6 via CLI)."""
from freqtrade.strategy import DecimalParameter
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT4_C3(OPT4_VolatilitySystem):
    signal_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1, space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.0, 4.0, default=3.0, decimals=1, space="sell", optimize=False)
