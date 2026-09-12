# OPT5_RegO2 — Door-3 variant O2: no NEW entries while regime in {2, 3}
# (range + turbulent).
#
# CONFIRMATION variant of the Task-A attribution: range is the single biggest
# profit bucket (269 trades / +75.5k USDT / 50.5% of pool profit) and
# turbulent is thin-positive (+9.5k). Blocking entries in both regimes is
# expected to collapse profit — this run exists to verify that attribution
# conclusion with a live backtest rather than assume it.
from OPT5_RegO1 import OPT5_RegO1


class OPT5_RegO2(OPT5_RegO1):
    block_regimes = (2, 3)
