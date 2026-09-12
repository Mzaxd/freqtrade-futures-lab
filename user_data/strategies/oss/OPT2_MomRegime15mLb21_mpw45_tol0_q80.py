"""Phase-2 grid cell mpw45_tol0_q80: MAX_POSITION_WEIGHT=0.45, REGIME_TOLERANCE=0.0,
FUNDING_GATE_MODE='q80'.  Only these three class attributes differ from
OPT2_MomRegime15mLb21 (grid origin mpw45/tol0/abs = phase-1 winner)."""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT2_MomRegime15mLb21_mpw45_tol0_q80(OPT2_MomRegime15mLb21):
    MAX_POSITION_WEIGHT = 0.45
    REGIME_TOLERANCE = 0.0
    FUNDING_GATE_MODE = "q80"
