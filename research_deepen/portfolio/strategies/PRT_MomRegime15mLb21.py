"""PRT_MomRegime15mLb21 — portfolio-agent rerun wrapper of frozen Sleeve B.

Pure alias of the frozen phase-2 deliverable OPT2_MomRegime15mLb21
(mpw45 / tolm3 / abs re-applied at the bottom of that file).  No parameter,
logic or style change of any kind.  Exists only so the portfolio agent's
full-window (20210101-20240101) zip can be attributed unambiguously to this
sandbox when backtesting with --strategy-path research_deepen/portfolio/strategies.
"""
import sys
from pathlib import Path

_OSS = Path(__file__).resolve().parents[3] / "user_data" / "strategies" / "oss"
if str(_OSS) not in sys.path:
    sys.path.insert(0, str(_OSS))

from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21  # noqa: E402


class PRT_MomRegime15mLb21(OPT2_MomRegime15mLb21):
    """Frozen sleeve B verbatim (see parent docstring for provenance)."""
