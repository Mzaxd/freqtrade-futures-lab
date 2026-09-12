"""Phase-2 grid cell mpw35_tol0_abs: MAX_POSITION_WEIGHT=0.35, REGIME_TOLERANCE=0.0,
FUNDING_GATE_MODE='abs'. (mpw35 replaces the structurally invalid mpw30:
cap 0.30 < equal-weight target 1/TOP_N=0.333 causes perpetual trim/add churn.)"""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT2_MomRegime15mLb21_mpw35_tol0_abs(OPT2_MomRegime15mLb21):
    MAX_POSITION_WEIGHT = 0.35
    REGIME_TOLERANCE = 0.0
    FUNDING_GATE_MODE = "abs"
