"""V2 bull_ladder — dual-speed regime ladder (pre_reg.md #V2, falsification
control): half basket in [SMA100, SMA100x1.03), full above."""
from bull_base import BullBase


class BullLadder(BullBase):
    LADDER_ENABLE = True
