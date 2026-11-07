"""V1 bull_fastre_half — deep-bear fast re-entry at HALF size (pre_reg.md #V1).
Standard gate unchanged; the fast channel only fires after >=250 days of
regime deprivation with BTC above its SMA50 (2023-01-05 pattern)."""
from bull_base import BullBase


class BullFastreHalf(BullBase):
    FAST_ENABLE = True
    FAST_SCALE = 0.5
