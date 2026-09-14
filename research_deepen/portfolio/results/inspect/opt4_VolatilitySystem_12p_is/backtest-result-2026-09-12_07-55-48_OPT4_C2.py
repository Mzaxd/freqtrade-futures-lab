"""Merge candidate C2: OPT1 original defaults 2.0/2.0 x atr08 gate x ts60 (MOT6 via CLI)."""
from freqtrade.strategy import DecimalParameter
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT4_C2(OPT4_VolatilitySystem):
    signal_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1, space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.0, 4.0, default=2.0, decimals=1, space="sell", optimize=False)
