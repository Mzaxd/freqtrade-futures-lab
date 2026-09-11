# v1.1 (TrendBaselineV1b) - single change vs v1: trading timeframe 1h -> 4h.
# Rationale (from IS diagnosis): on 1h the EMA cross system trades ~every 18h per
# pair with avg hold ~5h; taker fees (2x0.05%) + funding then dominate the thin
# per-trade edge. Moving to 4h cuts trade count ~4x and lengthens holds.
# Everything else (entries, exits, sizing, risk) identical to v1.
from TrendBaselineV1 import TrendBaselineV1


class TrendBaselineV1b(TrendBaselineV1):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    startup_candle_count = 400
