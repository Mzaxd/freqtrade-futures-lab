"""Hyperopt-A winner validation strategies (research_ab, 2026-11-04).

Explicit, byte-reproducible subclasses of OPT9_Hpt (user_data/strategies/oss/
OPT9_Hpt.py) pinning the pre-registered validation points. Every parameter
keeps its OPT9_Hpt grid but with optimize=False and default set to the
winner value: deterministic in backtesting (freqtrade uses the default when
not optimizing; optimize=False removes it from any hyperopt space). The grid
is kept visible so each class documents what was chosen from what menu.

Naming: HptA_S<k> = k-th best distinct-outcome combo of the Sharpe run
        HptA_C<k> = k-th best distinct-outcome combo of the Calmar run
        HptA_BASE = the frozen baseline point (regression guard: must
                    reproduce ARL_2x trade-for-trade on every window).

Run with: --strategy-path research_ab/hptA_strategies
"""
import sys
from pathlib import Path

_OSS = Path(__file__).resolve().parents[2] / "user_data" / "strategies" / "oss"
if str(_OSS) not in sys.path:
    sys.path.insert(0, str(_OSS))

from freqtrade.strategy import (  # noqa: E402
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
)

from OPT9_Hpt import OPT9_Hpt  # noqa: E402


# --- frozen baseline point (OPT1/OPT9/ARL_2x defaults) — regression guard ---
class HptA_BASE(OPT9_Hpt):
    """Frozen baseline point; must match ARL_2x trade-for-trade (3/2.0/2.0/2/24/48)."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.0, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)


# --- Sharpe run winners (distinct outcomes, loss ascending) -----------------
class HptA_S1(OPT9_Hpt):
    """Sharpe #1: loss -1.8646 (IS daily-Sharpe 1.865), IS +424.9%/DD 13.50/140 trades."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.25, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=3.0, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=3, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=48, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=72, space="sell",
                                         optimize=False)


class HptA_S2(OPT9_Hpt):
    """Sharpe #2: loss -1.8522, IS +547.8%/DD 12.63/147."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.25, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.5, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=3, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=48, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=72, space="sell",
                                         optimize=False)


class HptA_S3(OPT9_Hpt):
    """Sharpe #3: loss -1.8512, IS +418.7%/DD 13.50/138 (circuit back at 2)."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.25, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=3.0, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=48, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=72, space="sell",
                                         optimize=False)


class HptA_S4(OPT9_Hpt):
    """Sharpe #4: loss -1.8383, IS +538.8%/DD 12.63/145."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.25, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.5, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)


class HptA_S5(OPT9_Hpt):
    """Sharpe #5: loss -1.8294, IS +677.2%/DD 12.06/153."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.25, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.25, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=3, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=24, space="sell",
                                         optimize=False)


# --- Calmar run winners (distinct outcomes, loss ascending) -----------------
class HptA_C1(OPT9_Hpt):
    """Calmar #1: loss -157.73 (IS closed-trade Calmar 157.7), IS +1291.7%/DD 14.29/226."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=1.75, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=3, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=48, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=24, space="sell",
                                         optimize=False)


class HptA_C2(OPT9_Hpt):
    """Calmar #2: loss -154.78, IS +1267.6%/DD 14.29/223 (circuit back at 2)."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=1.75, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=48, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)


class HptA_C3(OPT9_Hpt):
    """Calmar #3: loss -154.22, IS +1234.0%/DD 13.96/210 (only P2 off-default)."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.0, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=3, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=48, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)


class HptA_C4(OPT9_Hpt):
    """Calmar #4: loss -153.83, IS +1027.7%/DD 11.66/205."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.25, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=3, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=72, space="sell",
                                         optimize=False)


class HptA_C5(OPT9_Hpt):
    """Calmar #5: loss -151.98, IS +1015.3%/DD 11.66/203."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.25, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)


# --- one-knob attribution variants (not winners; decomposition probes) -------
class HptA_D1(OPT9_Hpt):
    """Attribution: signal 2.0->2.25 ONLY (stop 2.0, P2 at frozen defaults)."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.25, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.0, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)


class HptA_D2(OPT9_Hpt):
    """Attribution: stop 2.0->2.5 ONLY (signal 2.0, P2 at frozen defaults)."""
    resample_hours = IntParameter(2, 6, default=3, space="buy", optimize=False)
    signal_atr_mult = DecimalParameter(1.5, 2.5, default=2.0, decimals=2,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.5, 3.0, default=2.5, decimals=2,
                                     space="sell", optimize=False)
    cluster_stop_count = CategoricalParameter([2, 3], default=2, space="sell",
                                              optimize=False)
    cluster_window_h = CategoricalParameter([24, 48], default=24, space="sell",
                                            optimize=False)
    circuit_hours = CategoricalParameter([24, 48, 72], default=48, space="sell",
                                         optimize=False)
