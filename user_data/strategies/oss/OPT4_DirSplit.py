"""Direction-split variants of sleeve A (OPT4) — decomposition experiment.

Question under test (2026-11-03): if A's LONG engine is replaced by sleeve B's
momentum-basket longs, does the hybrid (B longs + A shorts) beat A or AB?
These subclasses isolate each side by blocking entries of the other direction
in confirm_trade_entry. Signals, stops, sizing: byte-identical to OPT4.

Note: MOT slot / wallet interactions mean L3 + S3 != A3 exactly; treat the
split as a decomposition lens, and the hybrid as a fresh two-sleeve portfolio.
"""
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT4_ShortOnly(OPT4_VolatilitySystem):
    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        return side == "short"


class OPT4_LongOnly(OPT4_VolatilitySystem):
    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        return side == "long"
