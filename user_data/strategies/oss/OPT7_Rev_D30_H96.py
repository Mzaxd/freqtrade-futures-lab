"""OPT7_Rev_D30_H96 — Stage 2 cell (D x H96): DISLOCATION -0.30, HOLD 96h, long-only."""
from OPT7_ReversionBase import OPT7_ReversionBase


class OPT7_Rev_D30_H96(OPT7_ReversionBase):
    DISLOCATION = -0.30
    HOLD_HOURS = 96
    SHORT_SIDE = False
