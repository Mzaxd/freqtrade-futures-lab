# OPT5 door-1 variant ER1h-025: second gate = 1h Kaufman ER(28) >= 0.25.
from OPT5_GateBase import OPT5_GateBase


class OPT5_Gate_ER1h025(OPT5_GateBase):
    gate2_kind = "er1h"
    gate2_er_min = 0.25
