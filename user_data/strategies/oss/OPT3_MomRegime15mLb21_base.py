"""OPT3_MomRegime15mLb21_base — phase-3 baseline reproduction cell.

Both phase-3 levers explicitly OFF (= the OPT3 inherited defaults): sizing and
signals are identical to the phase-2 final OPT2_MomRegime15mLb21 (mpw45/tolm3/
abs).  Pre-registered cross-check: this cell must reproduce the phase-2 final
(52 trades / +590.93% / maxDD 16.81% / Sharpe 0.31 / PF 2.18 / funding
-11,307) within +-0.5% profit, otherwise the implementation is wrong and the
grid is void.
"""
from OPT3_MomRegime15mLb21 import OPT3_MomRegime15mLb21


class OPT3_MomRegime15mLb21_base(OPT3_MomRegime15mLb21):
    VOL_TARGET_ENABLE = False
    TRANSITION_BAND_ENABLE = False
