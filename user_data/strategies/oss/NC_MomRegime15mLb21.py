"""NC_MomRegime15mLb21 — the lb=21 variant of NC_MomRegime15mFast.

The repo's own docstring research (Basket/MomentumRegimeBasket15mFast.py) argues
lb=21 is the only lookback strong in every regime (1st/1st/2nd across P1/P2/P3
vs lb=14's 5th/2nd/1st) and flags lb=14 as "a P3 artifact, NOT validated
cross-regime". lb=21/N=9 was also the best-supported cell of the joint
lb x EXIT_RANK_N robustness grid. This file tests that open decision on the
lab's BTC/ETH/SOL futures universe. ONLY MOM_LOOKBACK_DAYS differs.
"""
from __future__ import annotations

from NC_MomRegime15mFast import NC_MomRegime15mFast


class NC_MomRegime15mLb21(NC_MomRegime15mFast):
    MOM_LOOKBACK_DAYS = 21   # 14 -> 21: the repo's robustness-preferred lookback
