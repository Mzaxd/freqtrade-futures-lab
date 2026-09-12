"""Phase-4 sensitivity neighbour: signal=sns20_21 2.0 2.1 stop= (centre 2.0/2.0, MOT4)."""
from freqtrade.strategy import DecimalParameter
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT4_(OPT4_VolatilitySystem):
    signal_atr_mult = DecimalParameter(1.0, 4.0, default=sns20_21 2.0 2.1, decimals=1, space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.0, 4.0, default=, decimals=1, space="sell", optimize=False)
