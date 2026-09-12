# OPT5 door-1 variant MLC: second gate = 12h EMA(50) slope direction filter
# (long entries need a rising 12h EMA50, short entries a falling one).
from OPT5_GateBase import OPT5_GateBase


class OPT5_Gate_MLC(OPT5_GateBase):
    gate2_kind = "mlc"
