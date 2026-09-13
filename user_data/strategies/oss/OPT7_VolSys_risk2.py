"""Phase-7 experiment: OPT4 with risk_pct 2% (leverage stays 2x). The REAL aggression dial."""
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT7_VolSys_risk2(OPT4_VolatilitySystem):
    risk_pct = 0.02
