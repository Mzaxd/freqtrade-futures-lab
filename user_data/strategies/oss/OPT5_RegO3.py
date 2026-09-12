# OPT5_RegO3 — Door-3 variant O3: halve (x0.5) the sized stake for NEW entries
# whose signal candle regime == 3 (turbulent) — reduce instead of forbid.
#
# The regime lookup uses the same signal candle (last closed 1h candle before
# the entry order) as the O1/O2 entry gate, so the overlay decision is on one
# consistent causal frame. Exits and stop logic are untouched; freqtrade may
# still lift a sub-minimum result stake back to the exchange minimum.
from freqtrade.persistence import Trade

from OPT5_RegimeBase import OPT5_RegimeBase


class OPT5_RegO3(OPT5_RegimeBase):
    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                            proposed_stake: float, min_stake: float | None,
                            max_stake: float, leverage: float, entry_tag,
                            side: str, **kwargs) -> float:
        stake = super().custom_stake_amount(
            pair, current_time, current_rate, proposed_stake, min_stake,
            max_stake, leverage, entry_tag, side, **kwargs)
        try:
            df, idx = self._signal_candle(pair, current_time)
            if idx >= 0 and int(df.iloc[idx]["regime"]) == 3:
                return stake * 0.5
        except Exception:
            pass
        return stake
