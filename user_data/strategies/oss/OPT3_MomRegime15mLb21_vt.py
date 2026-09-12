"""OPT3_MomRegime15mLb21_vt — phase-3 cell: per-coin volatility targeting ON.

target_i = (PV / TOP_N) * min(1, vol_ref / vol_i) with vol_i = 30-day daily
log-return std on the causal `known` panel and vol_ref the same-day
cross-sectional median.  Scale <= 1 => scaled target stays <= PV/TOP_N <
MAX_POSITION_WEIGHT (0.45).  See OPT3_MomRegime15mLb21 for causality details.
"""
from OPT3_MomRegime15mLb21 import OPT3_MomRegime15mLb21


class OPT3_MomRegime15mLb21_vt(OPT3_MomRegime15mLb21):
    VOL_TARGET_ENABLE = True
    TRANSITION_BAND_ENABLE = False
