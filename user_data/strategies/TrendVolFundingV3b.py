# v3.1 (TrendVolFundingV3b) - single change vs v3: trading timeframe 1h -> 4h.
# vol_lookback is rescaled 720h -> 180 bars (180 x 4h = 30 days, same real-time
# window). Funding informative stays 8h (> 4h strategy timeframe, valid).
# Everything else identical to v3.
from TrendVolFundingV3 import TrendVolFundingV3


class TrendVolFundingV3b(TrendVolFundingV3):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    startup_candle_count = 400
    vol_lookback = 180  # 180 x 4h = 30 days
    vol_min_periods = 60
