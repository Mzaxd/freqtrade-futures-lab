"""Phase-2 grid cell mpw35_tolm3_abs: MAX_POSITION_WEIGHT=0.35, REGIME_TOLERANCE=-0.03
(risk-on requires BTC >= 3% above SMA100), FUNDING_GATE_MODE='abs'."""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT2_MomRegime15mLb21_mpw35_tolm3_abs(OPT2_MomRegime15mLb21):
    MAX_POSITION_WEIGHT = 0.35
    REGIME_TOLERANCE = -0.03
    FUNDING_GATE_MODE = "abs"
