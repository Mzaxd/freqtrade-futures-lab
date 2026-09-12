# OPT5 door-2 variant LIM-prem: entry order = LIMIT at the signal candle's
# close x (1 +/- 0.001) — pay a 0.1% premium through the limit for immediacy
# (long bids 0.1% above the signal close, short offers 0.1% below).
# Same verified backtest semantics as OPT5_Exec_LIM_passive (see its header).
from OPT5_Exec_LIM_passive import OPT5_Exec_LIM_passive


class OPT5_Exec_LIM_prem(OPT5_Exec_LIM_passive):
    entry_premium = 0.001
