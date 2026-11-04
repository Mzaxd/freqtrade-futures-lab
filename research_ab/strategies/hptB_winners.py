"""hptB_winners.py — post-hoc interaction cells + final winner candidates for
research_ab Hyperopt-B.  Selected AFTER seeing the pre-registered OAT grid
(research_ab/results/hptB_grid_losses.csv) — a selection effect that is
disclosed in hyperopt_B.md.  Winners are frozen here for the three-window
validation backtests.

Post-hoc interactions (IS-window motivation):
  X1 = P20 + M60 : PER_COIN_SMA=20 was the best Sharpe-loss cell with the
      lowest MTM DD; MAX_POSITION_WEIGHT=0.60 was the best Calmar-loss and
      MTM-Sharpe cell.  Test whether they compose.
  X2 = Tm02 + M60: REGIME_TOLERANCE=-0.02 was the best regime-tolerance cell
      on Calmar with unchanged MTM DD; combine with M60.

Final winner candidates (chosen from OAT grid + interactions, see report):
  WB_SHARPE : lowest SharpeHyperOptLossDaily loss
  WB_CALMAR : lowest CalmarHyperOptLoss loss
"""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class X1(OPT2_MomRegime15mLb21):
    PER_COIN_SMA = 20
    MAX_POSITION_WEIGHT = 0.60


class X2(OPT2_MomRegime15mLb21):
    REGIME_TOLERANCE = -0.02
    MAX_POSITION_WEIGHT = 0.60


# --- final winner candidates (chosen from OAT grid + X1/X2 interactions;
#     numbers in research_ab/results/hptB_grid_losses.csv) ---
# SharpeHyperOptLossDaily winner: P20 cell, sharpe_loss -1.451 vs baseline -0.954
class WB_SHARPE(OPT2_MomRegime15mLb21):
    PER_COIN_SMA = 20


# CalmarHyperOptLoss winner: X2 cell, calmar_loss -1057.6 vs baseline -539.4
class WB_CALMAR(OPT2_MomRegime15mLb21):
    REGIME_TOLERANCE = -0.02
    MAX_POSITION_WEIGHT = 0.60
