# OPT7_NFIX7Probe — Phase 7 S1 family-inventory / ablation vehicle for NFI X7.
#
# Purpose: run the unmodified NostalgiaForInfinityX7 signal engine WITHOUT its
# profit engine (DCA/grind/derisk disabled, leverage 1x, uniform stake), so that
# per-family entry tags can be inventoried and ablated.
#
# Design:
#   - Subclass NostalgiaForInfinityX7; all indicators/entry logic inherited
#     verbatim (enter_tag records the family ids, e.g. "141 142 ").
#   - position_adjustment_enable = False (lab rule: no DCA/martingale/grid).
#     X7's adjust_trade_position already returns None when this is False.
#   - leverage() -> 1.0 (X7 hardcodes 3.0 in futures; we want the unlevered view).
#   - custom_stake_amount -> proposed_stake (drop X7's per-mode stake multipliers
#     so families are compared at equal stake).
#   - X7's own custom_exit stays (probe = "NFI signals through NFI exits, no DCA").
#   - Family selection via environment variables read at class-definition time
#     (each backtest is a fresh process):
#       OPT7_LONG_FAMILIES="141,142"  -> only these long families enabled
#       OPT7_LONG_FAMILIES="none"     -> all long families disabled
#       OPT7_SHORT_FAMILIES="562" / "none" (same semantics)
#     Unset variables leave X7's default enables untouched.
#
# This file is a research probe, NOT a candidate strategy. No lookahead added:
# entry/exit timing logic is inherited 1:1 from X7.
import os

from datetime import datetime

try:  # direct import when strategies dir is on PYTHONPATH
    from NostalgiaForInfinityX7 import NostalgiaForInfinityX7
except ImportError:  # relative import fallback
    from user_data.strategies.oss.NostalgiaForInfinityX7 import NostalgiaForInfinityX7


def _apply_family_selection(params: dict, env_var: str):
    raw = os.environ.get(env_var)
    if raw is None:
        return  # keep defaults
    enabled_ids = set()
    for tok in raw.replace(";", ",").split(","):
        tok = tok.strip()
        if tok:
            enabled_ids.add(tok)
    for key in params:
        fam = key.rsplit("_", 2)[1]
        params[key] = (fam in enabled_ids)


class OPT7_NFIX7Probe(NostalgiaForInfinityX7):
    """
    X7 signal engine, DCA stripped, 1x, uniform stake. Family sets via env.
    """

    INTERFACE_VERSION = 3

    position_adjustment_enable = False
    max_entry_position_adjustment = 0

    # own copies so we never mutate X7's class dicts
    long_entry_signal_params = dict(NostalgiaForInfinityX7.long_entry_signal_params)
    short_entry_signal_params = dict(NostalgiaForInfinityX7.short_entry_signal_params)
    _apply_family_selection(long_entry_signal_params, "OPT7_LONG_FAMILIES")
    _apply_family_selection(short_entry_signal_params, "OPT7_SHORT_FAMILIES")

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag,
        side: str,
        **kwargs,
    ) -> float:
        return 1.0

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake,
        max_stake: float,
        leverage: float,
        entry_tag,
        side: str,
        **kwargs,
    ) -> float:
        if min_stake is not None and proposed_stake < min_stake:
            return min_stake
        return proposed_stake
