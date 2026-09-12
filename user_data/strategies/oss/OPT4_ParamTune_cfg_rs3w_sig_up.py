# OPT4_ParamTune_cfg_rs3w_sig_up — fixed parameter variant for 12-coin validation.
# resample_hours=3h signal_atr_mult=2.0 stop_atr_mult=3.0
from freqtrade.strategy import DecimalParameter

from OPT4_ParamTune import OPT4_ParamTune


class OPT4_ParamTune_cfg_rs3w_sig_up(OPT4_ParamTune):
    resample_hours = 3
    signal_atr_mult = DecimalParameter(1.2, 3.5, default=2.0, decimals=1,
                                       space="buy", optimize=False)
    stop_atr_mult = DecimalParameter(1.2, 4.0, default=3.0, decimals=1,
                                     space="sell", optimize=False)
