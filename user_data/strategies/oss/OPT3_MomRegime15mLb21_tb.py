"""OPT3_MomRegime15mLb21_tb — phase-3 cell: regime transition band ON.

While BTC's known daily close is in [sma*(1-tol), sma*(1-tol+0.05)) =
[sma*1.03, sma*1.08) for tol=-0.03 — i.e. JUST after the risk-on threshold
flips — every sizing target halves (fresh entries start at half size;
accumulation toward a halved target).  Anchored at the ACTUAL inherited
risk-on threshold (1 - tol), not at the task text's literal (1 + tol)=0.97:
see the ANCHORING DISCLOSURE in OPT3_MomRegime15mLb21 (the literal band is
provably disjoint from every held candle and would be a no-op identical to
`base`).
"""
from OPT3_MomRegime15mLb21 import OPT3_MomRegime15mLb21


class OPT3_MomRegime15mLb21_tb(OPT3_MomRegime15mLb21):
    VOL_TARGET_ENABLE = False
    TRANSITION_BAND_ENABLE = True
