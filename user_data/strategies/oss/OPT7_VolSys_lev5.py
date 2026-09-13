"""Phase-7 experiment: OPT4 with leverage 5x (risk-based sizing unchanged)."""
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT7_VolSys_lev5(OPT4_VolatilitySystem):
    leverage_fixed = 5.0
