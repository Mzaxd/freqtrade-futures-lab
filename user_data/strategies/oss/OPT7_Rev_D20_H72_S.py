"""OPT7_Rev_D20_H72_S — Stage 2 cell (D x short side on): long DISLOCATION -0.20,
short mirror +0.20 (RSI(14) crosses above 70 AND price >20% above 50d SMA),
both sides exit on the same 72h time rule."""
from OPT7_ReversionBase import OPT7_ReversionBase


class OPT7_Rev_D20_H72_S(OPT7_ReversionBase):
    DISLOCATION = -0.20
    HOLD_HOURS = 72
    SHORT_SIDE = True
    SHORT_DISLOCATION = 0.20
