"""OPT3_MomRegime15mLb21_vttb — phase-3 cell: BOTH levers ON (vt x tb).

target_i = (PV / TOP_N) * min(1, vol_ref / vol_i) * 0.5[in transition band].
The two multipliers are independent by construction (vol is per-coin, the band
is a per-date row scalar) and compose multiplicatively in the cached scale
panel.  Still <= PV/TOP_N < MAX_POSITION_WEIGHT.
"""
from OPT3_MomRegime15mLb21 import OPT3_MomRegime15mLb21


class OPT3_MomRegime15mLb21_vttb(OPT3_MomRegime15mLb21):
    VOL_TARGET_ENABLE = True
    TRANSITION_BAND_ENABLE = True
