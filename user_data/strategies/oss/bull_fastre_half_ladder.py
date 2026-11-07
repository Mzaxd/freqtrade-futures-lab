"""V3 bull_fastre_half_ladder — V1 fast channel + V2 ladder combined
(pre_reg.md #V3)."""
from bull_base import BullBase


class BullFastreHalfLadder(BullBase):
    FAST_ENABLE = True
    FAST_SCALE = 0.5
    LADDER_ENABLE = True
