# OPT5 door-1 variant ER1h-030: second gate = 1h Kaufman ER(28) >= 0.30.
from OPT5_GateBase import OPT5_GateBase


class OPT5_Gate_ER1h030(OPT5_GateBase):
    gate2_kind = "er1h"
    gate2_er_min = 0.30
