"""AB leverage grid (2026-11-04) — test "does raising leverage amplify profits?"
on the pre-registered A70/B30 + recycle(1.21) configuration, 3-pair universe.

Mechanical fact (babfdfe research, re-tested here): A's notional formula
`equity * risk_pct / stop_pct` contains NO leverage term — leverage only sets
margin per position. So lev 3x/5x at the same risk_pct is PnL-neutral EXCEPT
for the new failure mode it introduces: liquidation. 2x liquidation distance
is ~49.5% (EXEC-verified 0/436 breaches); 3x ~33%, 5x ~20% — while A's ATR
stops reach 18.7% (WS1) and B holds through drawdowns with no stops at all.

Grid:
  A side (all RECYCLE_MULT=1.21):
    ARL_2x    lev 2.0, risk 1%   — baseline (= pre-registered config)
    ARL_3x    lev 3.0, risk 1%   — leverage alone
    ARL_5x    lev 5.0, risk 1%   — leverage alone, inside liquidation territory
    ARL_2x_r2 lev 2.0, risk 2%   — the "real dial" amplification (notional x2)
  B side (leverage method added; B's notional target = equity/TOP_N unchanged):
    BL_3x / BL_5x
"""
from OPT9_Recycle import OPT9_Recycle
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class ARL_2x(OPT9_Recycle):
    RECYCLE_MULT = 1.21
    leverage_fixed = 2.0


class ARL_3x(OPT9_Recycle):
    RECYCLE_MULT = 1.21
    leverage_fixed = 3.0


class ARL_5x(OPT9_Recycle):
    RECYCLE_MULT = 1.21
    leverage_fixed = 5.0


class ARL_2x_r2(ARL_2x):
    risk_pct = 0.02


class BL_3x(OPT2_MomRegime15mLb21):
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(3.0, max_leverage)


class BL_5x(BL_3x):
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(5.0, max_leverage)


class BL_2x(OPT2_MomRegime15mLb21):
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(2.0, max_leverage)
