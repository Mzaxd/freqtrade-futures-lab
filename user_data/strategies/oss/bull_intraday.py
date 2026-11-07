"""V5 bull_intraday — regime gate on the live 15m BTC close vs yesterday's
SMA100x1.03 (pre_reg.md #V5): removes the 1-day stale-close lag."""
from bull_base import BullBase


class BullIntraday(BullBase):
    INTRADAY_REGIME = True
