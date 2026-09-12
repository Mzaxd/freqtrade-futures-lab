# OPT4_ParamTune_rs6 — layered campaign: resample_hours fixed at 6.
# Hyperopt only searches signal_atr_mult (buy) / stop_atr_mult (sell).
from OPT4_ParamTune import OPT4_ParamTune


class OPT4_ParamTune_rs6(OPT4_ParamTune):
    resample_hours = 6
