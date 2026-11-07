"""V1f bull_fastre_full — deep-bear fast re-entry at FULL size (pre_reg.md #V1f).
Same channel as V1 but the latch carries a full-size basket."""
from bull_base import BullBase


class BullFastreFull(BullBase):
    FAST_ENABLE = True
    FAST_SCALE = 1.0
