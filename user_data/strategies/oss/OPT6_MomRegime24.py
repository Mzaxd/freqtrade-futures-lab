"""OPT6_MomRegime24 — Phase-6 door-M universe extension of the frozen MomRegime form.

Everything is inherited VERBATIM from OPT2_MomRegime15mLb21 with the phase-2
final candidate's parameters applied at that file's bottom (lb=21, mpw45,
tolm3, abs funding gate 0.0005, TOP_N=3).  This subclass exists ONLY so the
backtest result carries a distinct strategy key for the 24-coin universe:

  12 old: BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI
  11 new: ATOM FIL VET ETC XLM TRX BCH THETA IOTA AAVE NEAR

Run protocol (phase 6): 15m, --max-open-trades 3 (== TOP_N), all 24 pairs
passed via --pairs.  The cross-sectional ranking, hysteresis and daily panels
discover coins by name from FEATHER_DIR, so no code change is needed for the
wider universe.

Funding disclosure (2026-09-12): all 11 new coins now have 1h funding feathers
(downloaded this phase within the 20210101-20240101 command window; files on
disk extend slightly past 2024-01-01 but backtest loading is trimmed to the
backtest timerange, and opt_common's merge is strictly backward/as-of, so no
future rate can ever be observed).  Within-window coverage was verified.  LTC
and UNI still have no funding feather -> their funding gate is NaN-pass,
exactly as in the 12-coin reference form.
"""
from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT6_MomRegime24(OPT2_MomRegime15mLb21):
    """Frozen MomRegime form on the 24-coin universe. No logic changes."""
    pass
