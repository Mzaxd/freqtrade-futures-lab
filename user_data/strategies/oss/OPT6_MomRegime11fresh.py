"""OPT6_MomRegime11fresh — Phase-6 door-M migration test: the frozen MomRegime
form on ONLY the 11 fresh coins (ATOM FIL VET ETC XLM TRX BCH THETA IOTA AAVE
NEAR), never used in any prior selection round.

Parameters are inherited verbatim from OPT2_MomRegime15mLb21 (lb=21, mpw45,
tolm3, abs funding gate 0.0005, TOP_N=3).  Run protocol: 15m,
--max-open-trades 3, the 11 pairs via --pairs.

Implementation caveat handled HERE (the only delta vs the parent): the frozen
form's risk-on gate is `BTC daily close > SMA100 * (1 + 0.03)` — BTC is the
regime REFERENCE, not a tradable member.  The parent derives that gate from
the whitelist's daily panel, so on a BTC-less whitelist it would silently
degenerate to risk_on = always True (REGIME_TOLERANCE=-0.03 would become a
no-op and the test would no longer be the frozen form).  This subclass keeps
the frozen form intact by feeding the BTC daily close from the SAME feather
source the parent already uses for every other daily input:

  _daily_closes() additionally loads the REGIME_REF column from
  FEATHER_DIR/<BTC>_USDT_USDT-1d-futures.feather when BTC is not tradable.

The extra column only powers `btc_d` / the risk-on Series in _compute_xs; the
15m close panel P15 (momentum ranking + basket membership + per-coin SMA gate)
is built by the parent strictly from the tradable whitelist, so BTC itself can
never be ranked, held or traded.  Causality is unchanged: the feather panel is
lagged one day (known = Pd.shift(1)) exactly like every other daily input.

Funding disclosure (2026-09-12): all 11 fresh coins have 1h funding feathers
(downloaded this phase; command window 20210101-20240101, backward as-of merge
only).  Within-window coverage was verified.
"""
from __future__ import annotations

import pandas as pd

from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT6_MomRegime11fresh(OPT2_MomRegime15mLb21):
    """Frozen MomRegime form on the 11-coin fresh universe (BTC regime gate
    kept active from daily feathers; BTC itself not tradable)."""

    def _daily_closes(self, pairs) -> pd.DataFrame:
        out = super()._daily_closes(pairs)
        if self.REGIME_REF not in out.columns:
            ref_panel = super()._daily_closes([self.REGIME_REF])
            if self.REGIME_REF in ref_panel.columns:
                out = pd.concat([out, ref_panel[[self.REGIME_REF]]], axis=1).sort_index()
        return out
