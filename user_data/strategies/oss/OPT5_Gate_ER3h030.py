# OPT5 door-1 variant ER3h-030: second gate = 3h-resampled Kaufman ER(14) >= 0.30.
from OPT5_GateBase import OPT5_GateBase


class OPT5_Gate_ER3h030(OPT5_GateBase):
    gate2_kind = "er3h"
    gate2_er_min = 0.30
