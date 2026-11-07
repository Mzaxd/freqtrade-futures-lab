"""bull_2x — B2x overlay on the BULL champion (BullFastreFull): the only
delta vs the champion is the leverage() dial at 2x (known sweet spot from
the lvg leverage map).  Structure/gates untouched."""
from bull_fastre_full import BullFastreFull


class Bull2x(BullFastreFull):
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(2.0, max_leverage)
