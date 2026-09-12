# OPT4_ParamTune_rs2 — layered campaign: resample_hours fixed at 2.
# Hyperopt only searches signal_atr_mult (buy) / stop_atr_mult (sell).
from OPT4_ParamTune import OPT4_ParamTune


class OPT4_ParamTune_rs2(OPT4_ParamTune):
    resample_hours = 2
