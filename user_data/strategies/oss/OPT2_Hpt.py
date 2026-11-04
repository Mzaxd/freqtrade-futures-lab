"""OPT2_Hpt — hyperopt wrapper for sleeve B (OPT2_MomRegime15mLb21), 3-coin universe.

RESEARCH FILE for research_ab Hyperopt-B (2026-11-04).  NOT a deployment
strategy: it exists only to expose the 3-coin-IDENTIFIABLE parameters of the
frozen sleeve-B baseline as freqtrade Parameters so `freqtrade hyperopt` can
search them.

Structural constraint (from B's own docstring, OPT1_MomRegime15mLb21):
on the 3-coin deployment universe TOP_N=3 makes rank<=TOP_N true for every
whitelisted pair at all times, so the cross-sectional ranking parameters
(MOM_LOOKBACK_DAYS, EXIT_RANK_N, TOP_N) are NOT identifiable on 3 coins (two
lookback variants produced byte-identical results).  They are deliberately
NOT hyperopted here.  Only parameters whose effect survives the 3-coin
degenerate ranking are searched:

  buy space (entry-gating):
    regime_sma       {50, 75, 100, 125, 150}   BTC bull/bear switch, daily bars
    per_coin_sma     {20, 30, 50, 75, 100}     held coin's own daily filter
    regime_tolerance {-0.03, -0.02, 0.0, 0.02} ron = btc > sma*(1-tol);
                     -0.03 included so the FROZEN BASELINE cell is inside the
                     grid (task grid was {-0.02, 0, +0.02}; baseline anchor
                     added, disclosed in hyperopt_B.md)
    funding_max_p    {0.0003, 0.0005, 0.0008, 1.0}  1.0 = disabled sentinel
                     (opt_common.funding_gate_long documents the sentinel)
  sell space (position management):
    max_position_weight {0.30, 0.45, 0.60}

Grid size 5*5*4*4*3 = 1200 cells.  QUOTE_VOLUME_HEADROOM_MULT is NOT searched
(minor effect, per task brief; kept at parent default 10.0).

Implementation notes (IMPORTANT for anyone reusing this pattern):
  * freqtrade Parameters are plain class attributes read via `.value` — the
    parent chain reads plain class attributes via `self.REGIME_SMA` etc., and
    those tracked files must not be modified.  So each Parameter is declared
    under a NEW name (e.g. `regime_sma`) and a read-through property exposes
    it under the PARENT's attribute name (`REGIME_SMA`), returning `.value`.
    Parameter discovery (strategy.hyper.detect_all_parameters) skips the
    properties (their getattr value is not a BaseParameter) and picks up the
    renamed Parameters.
  * regime_sma / per_coin_sma / regime_tolerance feed populate_indicators (the
    `hold` membership column) => hyperopt MUST run with --analyze-per-epoch,
    otherwise those three would be silently frozen (freqtrade only re-runs
    populate_entry/exit_trend per epoch by default; freqtrade also emits a
    'static use' warning in that case).
  * funding_max also gates ACCUMULATION adds and max_position_weight drives
    the trim branch, both inside adjust_trade_position — evaluated live by
    the backtesting engine each epoch, no extra plumbing needed.
  * Baseline defaults = frozen sleeve B: REGIME_SMA=100, PER_COIN_SMA=50,
    REGIME_TOLERANCE=-0.03, funding_max=0.0005, MAX_POSITION_WEIGHT=0.45
    (OPT2_MomRegime15mLb21 re-applies tol=-0.03 at the bottom of its file).
"""
from __future__ import annotations

from freqtrade.strategy import CategoricalParameter

from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT2_Hpt(OPT2_MomRegime15mLb21):
    """Parameter-ized sleeve B for hyperopt only (see module docstring)."""

    INTERFACE_VERSION = 1

    # --- buy space: membership / entry gating ---
    regime_sma = CategoricalParameter(
        [50, 75, 100, 125, 150], default=100, space="buy", optimize=True)
    per_coin_sma = CategoricalParameter(
        [20, 30, 50, 75, 100], default=50, space="buy", optimize=True)
    regime_tolerance = CategoricalParameter(
        [-0.03, -0.02, 0.0, 0.02], default=-0.03, space="buy", optimize=True)
    funding_max_p = CategoricalParameter(
        [0.0003, 0.0005, 0.0008, 1.0], default=0.0005, space="buy", optimize=True)

    # --- sell space: position management ---
    max_position_weight = CategoricalParameter(
        [0.30, 0.45, 0.60], default=0.45, space="sell", optimize=True)

    # --- read-through properties under the PARENT attribute names ---
    @property
    def REGIME_SMA(self):
        return self.regime_sma.value

    @property
    def PER_COIN_SMA(self):
        return self.per_coin_sma.value

    @property
    def REGIME_TOLERANCE(self):
        return self.regime_tolerance.value

    @property
    def funding_max(self):
        return self.funding_max_p.value

    @property
    def MAX_POSITION_WEIGHT(self):
        return self.max_position_weight.value

    # --- sampler override: freqtrade 2026.8 defaults to NSGAIIISampler, which is
    # multi-objective machinery wasted on a scalar loss and far less sample-
    # efficient at the ~30-epoch budget this experiment can afford.  TPE is the
    # classic single-objective default, returned as an INSTANCE with
    # n_startup_trials=6 (freqtrade's string shortcut would set 30 random
    # startup trials — more than this experiment's whole epoch budget).
    # Disclosed in hyperopt_B.md. ---
    class HyperOpt:
        @staticmethod
        def generate_estimator(dimensions, random_state=None, **kwargs):
            import optuna
            return optuna.samplers.TPESampler(seed=random_state, n_startup_trials=6)
