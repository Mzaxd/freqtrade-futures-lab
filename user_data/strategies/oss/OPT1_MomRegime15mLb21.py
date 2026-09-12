"""OPT1_MomRegime15mLb21 — the lb=21 variant of OPT1_MomRegime15mFast.

Rationale (from the source repo's own docstring research, cf. NC_MomRegime15mLb21):
lb=21 is the only lookback strong in every regime (1st/1st/2nd across P1/P2/P3
vs lb=14's 5th/2nd/1st); lb=21/N=9 was the best-supported cell of the joint
lb x EXIT_RANK_N robustness grid.  On the 3-coin lab universe the lb parameter
was unidentifiable (both variants produced byte-identical results because
rank<=TOP_N is always true for every whitelisted pair).  On the 12-coin
universe the cross-sectional ranking is discriminative, so this variant tests
lb identifiability directly.  ONLY MOM_LOOKBACK_DAYS differs; the OPT1 funding
gate (funding_max=0.0005) is inherited unchanged.
"""
from __future__ import annotations

from OPT1_MomRegime15mFast import OPT1_MomRegime15mFast


class OPT1_MomRegime15mLb21(OPT1_MomRegime15mFast):
    MOM_LOOKBACK_DAYS = 21   # 14 -> 21: the repo's robustness-preferred lookback
