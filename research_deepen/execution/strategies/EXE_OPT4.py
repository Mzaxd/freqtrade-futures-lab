# EXE_OPT4 — execution-model research subclass of the champion OPT4_VolatilitySystem.
#
# Pure `pass` subclass: identical signals/stops/sizing, distinct class name so the
# backtest result zip embedded strategy name is attributable to this sandbox
# (research_deepen/execution) even though several agents share the public
# user_data/backtest_results directory (CHARTER section 2.2/2.3).
#
# Parent import chain lives in user_data/strategies/oss (OPT4 -> OPT1 -> IStrategy);
# freqtrade does not add that directory to sys.path when --strategy-path points here.
import sys
from pathlib import Path

_OSS_DIR = Path(__file__).resolve().parents[3] / "user_data" / "strategies" / "oss"
if str(_OSS_DIR) not in sys.path:
    sys.path.insert(0, str(_OSS_DIR))

from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class EXE_OPT4(OPT4_VolatilitySystem):
    pass
