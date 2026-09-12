"""OPT7_Rev_D20_H72 — Stage 1 D-grid: DISLOCATION -0.20, HOLD 72h, long-only."""
from OPT7_ReversionBase import OPT7_ReversionBase


class OPT7_Rev_D20_H72(OPT7_ReversionBase):
    DISLOCATION = -0.20
    HOLD_HOURS = 72
    SHORT_SIDE = False
