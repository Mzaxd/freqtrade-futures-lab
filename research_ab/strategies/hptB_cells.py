"""hptB_cells.py — pre-registered one-at-a-time (OAT) mini-grid cells for
research_ab Hyperopt-B (sleeve B, 3-coin universe), evaluated by direct IS
backtests after the TPE hyperopt runs stalled on a pathological slow cell
(see research_ab/hyperopt_B.md for the full account).

Design (pre-registered 2026-11-04, BEFORE running these backtests):
  anchor B0 = frozen sleeve B baseline
      REGIME_SMA=100, PER_COIN_SMA=50, REGIME_TOLERANCE=-0.03,
      funding_max=0.0005, MAX_POSITION_WEIGHT=0.45
  each other cell changes EXACTLY ONE dimension vs B0:
    R50/R75/R125/R150  : REGIME_SMA
    P20/P30/P75/P100   : PER_COIN_SMA
    Tm02/T0/Tp02       : REGIME_TOLERANCE
    F03/F08/F10        : funding_max (F10 = 1.0 sentinel = gate off)
    M30/M60            : MAX_POSITION_WEIGHT
  Main effects read directly off the anchor-vs-cell deltas; interaction cells
  (post-hoc, disclosed as such) go into hptB_winners.py.

These are plain class-attribute overrides (no Parameters) so backtests are
pure frozen configurations — same pattern as the historical OPT2 grid files.
"""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21

# anchor (= frozen baseline; identical config to OPT2_MomRegime15mLb21)
class B0(OPT2_MomRegime15mLb21):
    pass


class R50(OPT2_MomRegime15mLb21):
    REGIME_SMA = 50


class R75(OPT2_MomRegime15mLb21):
    REGIME_SMA = 75


class R125(OPT2_MomRegime15mLb21):
    REGIME_SMA = 125


class R150(OPT2_MomRegime15mLb21):
    REGIME_SMA = 150


class P20(OPT2_MomRegime15mLb21):
    PER_COIN_SMA = 20


class P30(OPT2_MomRegime15mLb21):
    PER_COIN_SMA = 30


class P75(OPT2_MomRegime15mLb21):
    PER_COIN_SMA = 75


class P100(OPT2_MomRegime15mLb21):
    PER_COIN_SMA = 100


class Tm02(OPT2_MomRegime15mLb21):
    REGIME_TOLERANCE = -0.02


class T0(OPT2_MomRegime15mLb21):
    REGIME_TOLERANCE = 0.0


class Tp02(OPT2_MomRegime15mLb21):
    REGIME_TOLERANCE = 0.02


class F03(OPT2_MomRegime15mLb21):
    funding_max = 0.0003


class F08(OPT2_MomRegime15mLb21):
    funding_max = 0.0008


class F10(OPT2_MomRegime15mLb21):
    funding_max = 1.0     # sentinel: gate effectively disabled


class M30(OPT2_MomRegime15mLb21):
    MAX_POSITION_WEIGHT = 0.30


class M60(OPT2_MomRegime15mLb21):
    MAX_POSITION_WEIGHT = 0.60
