"""V4 bull_coinfast — asymmetric per-coin re-entry (pre_reg.md #V4): while the
standard regime is confirmed (x1.03), coins may ENTER above their SMA20;
the stay/exit trend gate remains SMA50."""
from bull_base import BullBase


class BullCoinFast(BullBase):
    COIN_FAST_SMA = 20
