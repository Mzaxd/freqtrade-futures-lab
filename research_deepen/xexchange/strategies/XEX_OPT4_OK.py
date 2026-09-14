# XEX_OPT4_OK — cross-exchange robustness wrapper (OKX futures data).
# Identical logic to user_data/strategies/oss/OPT4_VolatilitySystem.py, frozen
# parameters 2.0/2.0/0.8 gate/60d time stop/1% risk/2x. This subclass exists only
# to (a) import from the oss directory and (b) carry a distinct class name so
# result zips are attributable within the shared backtest_results directory.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "user_data" / "strategies" / "oss"))

from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class XEX_OPT4_OK(OPT4_VolatilitySystem):
    pass
