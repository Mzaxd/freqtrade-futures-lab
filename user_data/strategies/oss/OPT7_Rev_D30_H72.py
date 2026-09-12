"""OPT7_Rev_D30_H72 — Stage 1 D-grid control: DISLOCATION -0.30, HOLD 72h, long-only.

Logic-identical to NC_OversoldReversion but routed through OPT7_ReversionBase
(can_short=True machinery present, never triggered) — structural control to
separate inheritance plumbing from knob effects.
"""
from OPT7_ReversionBase import OPT7_ReversionBase


class OPT7_Rev_D30_H72(OPT7_ReversionBase):
    DISLOCATION = -0.30
    HOLD_HOURS = 72
    SHORT_SIDE = False
