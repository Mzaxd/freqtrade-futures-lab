# OPT5 door-1 CONTROL run: OPT4 frozen config through the OPT5_GateBase
# scaffolding with the second gate disabled — must reproduce the OPT4 baseline
# (+1495.84% / DD 15.92% / Sharpe 1.01 / 433 trades) exactly; any drift means
# the scaffolding itself perturbed the pipeline.
from OPT5_GateBase import OPT5_GateBase


class OPT5_Gate_None(OPT5_GateBase):
    gate2_kind = "none"
