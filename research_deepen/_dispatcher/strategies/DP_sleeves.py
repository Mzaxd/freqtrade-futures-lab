# DP_ prefixed subclasses for the 2024-26 disclosed deployment diagnostic.
# Zero parameter changes vs the frozen deliverables; unique class names only
# (parallel zip hygiene per CHARTER).
import sys
from pathlib import Path

_OSS = Path(__file__).resolve().parents[3] / "user_data" / "strategies" / "oss"
if str(_OSS) not in sys.path:
    sys.path.insert(0, str(_OSS))

from OPT4_VolatilitySystem import OPT4_VolatilitySystem
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21
from OPT7_NFILite import OPT7_NFILite


class DP_OPT4(OPT4_VolatilitySystem):
    pass


class DP_SleeveB(OPT2_MomRegime15mLb21):
    pass


class DP_NFILite(OPT7_NFILite):
    pass
