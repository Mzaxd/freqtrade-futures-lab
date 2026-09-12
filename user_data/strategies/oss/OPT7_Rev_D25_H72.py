"""OPT7_Rev_D25_H72 — Stage 1 D-grid: DISLOCATION -0.25, HOLD 72h, long-only."""
from OPT7_ReversionBase import OPT7_ReversionBase


class OPT7_Rev_D25_H72(OPT7_ReversionBase):
    DISLOCATION = -0.25
    HOLD_HOURS = 72
    SHORT_SIDE = False
