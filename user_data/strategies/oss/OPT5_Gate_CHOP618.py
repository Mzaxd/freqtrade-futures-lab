# OPT5 door-1 variant CHOP-618: second gate = 1h Choppiness(14) <= 61.8.
from OPT5_GateBase import OPT5_GateBase


class OPT5_Gate_CHOP618(OPT5_GateBase):
    gate2_kind = "chop"
    gate2_chop_max = 61.8
