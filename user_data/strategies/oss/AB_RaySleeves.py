"""AB single-coin research sleeves for RAYSOL (2026-11-07, user request).

Out-of-universe exploratory run: Raydium only, NOT part of the frozen AB
program (universe there = BTC/ETH/SOL). Nothing here touches frozen files.

AB_Ray_B — OPT2_MomRegime15mLb21 (frozen B) with ONE surgical override:
  B's BTC risk-on regime is read from the DAILY CLOSE PANEL built from the
  whitelist (`known.get(self.REGIME_REF)` in NC_MomRegime15mFast._compute_xs).
  On a RAY-only whitelist BTC is absent -> `btc_d is None` -> regime silently
  degrades to always-risk-on.  In every frozen universe BTC is whitelisted so
  this never fires there.  This subclass injects BTC's daily feather into the
  panel (panel-only; BTC is NOT tradable, its membership column is ignored by
  entry/exit which look up `want[pair]` for whitelisted pairs only), keeping
  the regime gate byte-equivalent to the frozen semantics.

Everything else verbatim frozen B: mpw45 / tol -0.03 / abs funding gate,
TOP_N=3 (a single coin occupies one of B's three slots -> target weight
pv/3, exactly what one coin gets in the 3-coin deployment), MOM14, SMA50
per-coin trend filter, liquidity caps.
"""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class AB_Ray_B(OPT2_MomRegime15mLb21):
    def _daily_closes(self, pairs) -> "object":
        # add the BTC regime reference to the panel even when it is not
        # whitelisted (single-coin research run) — see module docstring
        return super()._daily_closes(tuple(sorted(set(pairs) | {self.REGIME_REF})))
