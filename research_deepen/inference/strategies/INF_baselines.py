# INF_baselines — inference-hardening sandbox strategies (research_deepen/inference).
#
# INF_OPT4: byte-identical re-run wrapper of the frozen champion
# OPT4_VolatilitySystem (12-coin IS-pool reference: +1495.8% / DD 15.92% /
# Sharpe 1.01 / PF 1.97). No parameter or logic changes — the `pass` subclass
# only guarantees a unique class name so the exported zip can be attributed to
# this agent under the shared backtest_results directory (CHARTER zip hygiene).
#
# Sleeve B (OPT2_MomRegime15mLb21, frozen mpw45/tolm3/abs) and NFI-Lite
# (OPT7_NFILite, frozen tp75/stop3.0/hold48h/fam141-143) baselines are REUSED
# from the official frozen zips (opt2_MomRegime15mLb21_{is,val}.zip,
# opt7_lite_tc3_12p_is.zip) — their embedded strategy sources were verified to
# carry the frozen parameters, and 15m/5m data for the 12-coin pool is not on
# disk anymore, so re-running them is neither possible nor needed.
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_OSS_DIR = os.path.join(_REPO_ROOT, "user_data", "strategies", "oss")
if _OSS_DIR not in sys.path:
    sys.path.insert(0, _OSS_DIR)

from OPT4_VolatilitySystem import OPT4_VolatilitySystem  # noqa: E402


class INF_OPT4(OPT4_VolatilitySystem):
    """Frozen OPT4_VolatilitySystem, unique name for zip attribution."""

    pass
