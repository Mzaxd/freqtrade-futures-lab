"""Phase-7 experiment: OPT4 with faster signal (resample 2h instead of 3h), base stays 1h."""
from OPT4_VolatilitySystem import OPT4_VolatilitySystem
from freqtrade.strategy import IntParameter


class OPT7_VolSys1h_rs2(OPT4_VolatilitySystem):
    resample_hours = IntParameter(2, 6, default=2, space="buy", optimize=False)
