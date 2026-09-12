"""Phase-2 grid cell mpw35_tol0_q80: MAX_POSITION_WEIGHT=0.35, REGIME_TOLERANCE=0.0,
FUNDING_GATE_MODE='q80' (rolling 30d 80th-percentile funding gate)."""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT2_MomRegime15mLb21_mpw35_tol0_q80(OPT2_MomRegime15mLb21):
    MAX_POSITION_WEIGHT = 0.35
    REGIME_TOLERANCE = 0.0
    FUNDING_GATE_MODE = "q80"
