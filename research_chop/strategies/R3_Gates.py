"""R3_Gates — WS-R3 defensive sizing/entry-blocking overlays on sleeve A
(research_chop, 2026-11-04; PRE_REGISTRATION.md §2/§2.1, CONTEXT.md).

Everything here layers on the FROZEN A baseline ARL_2x (OPT9_Recycle@1.21,
lev 2). Signals (populate_*), stops (custom_stoploss), P2 cluster circuit and
the recycle sizing chain are BYTE-IDENTICAL to ARL_2x — only two hooks are
added, and both are pure sizing / entry-blocking:

  * market gates (contrast arms): in custom_stake_amount, gate ON at the last
    CLOSED 1h candle -> stake x 0.5 (= risk x 0.5). Gate OFF -> untouched.
      R3_G1h : g1 = |mom_z| < 1.25                      (negative control)
      R3_G2h : g2 = g1 AND atr_pct_rank >= 0.90         (violent chop)
      R3_G4h : g4 = >=90% of trailing 240 h had g1      (persistent range)
  * G3 failure-cluster gate (MAIN hypothesis, PRE §2):
      R3_C3h_N{N}_D{D}: >= N losing closes (profit_ratio < 0) on this
        (pair, side) within the last D days, counted AFTER that side's most
        recent profitable close ("直至该边出现盈利单"), -> stake x 0.5.
        State recomputed at every entry; no persistence.
      R3_C3p_N{N}_D{D}: the D-day loser cluster ending at the most recent
        loser reaches N -> block NEW entries on that (pair, side) for 7 days
        from that loser (time unlock; a same-side profitable close after the
        last loser lifts the pause early). P2's data-access idiom
        (Trade.get_trades_proxy, OPT9.confirm_trade_entry) re-anchored to
        per-pair / per-side with D-day density (PRE: "3 币密度重标定的 P2").

Causality of the market gates (WS3-verified pattern, OPT9_Recycle):
  dp.get_pair_dataframe(pair, '1h') returns the RAW frame cut at the current
  candle by freqtrade itself; we ADDITIONALLY slice strictly before
  current_time (searchsorted on the date column — drops the just-opened
  candle), then evaluate the label of the last closed candle. Label row t is
  computed only from candles closed at or before t (all windows trailing),
  i.e. it is the exact quantity exported by research_chop/scripts/
  regime_label.py to research_chop/data/regime_1h_*.csv; using it at decision
  time T >= t+1h respects the registered "row t valid from t+1 open" rule.
  Gates are recomputed from raw OHLCV — NEVER read from the label CSVs.

Tail-slice equivalence: every feature is a TRAILING window (<= 720 rows), so
labeling df.iloc[max(0, idx-800):idx+1] reproduces the full-history label at
row idx exactly (cheaper than relabeling the whole frame per entry; cache
keyed by (pair, idx)). Caveat kept from startup_candle_count=200 (inherited,
NOT raised — raising it would alter the analyzed-frame atr08 gate in the
first ~3 weeks of a window and thus touch entry signals, which is forbidden):
the raw frame starts only 200 h before the window, so for the first ~40 h of
each backtest window the rank/rolling windows are short (gates OFF =
baseline behavior) and g2's atr_pct_rank uses partial (240..719-row) windows
for the first ~520 h before converging to the CSV labels. g1 is exact from
candle 1 (needs 84 h), g4 is exact from hour 40 (needs 240 rows), all G3
variants need no market data at all. Disclosed in ws_r3_defense.md.

G3 trade-history semantics: "止损" is operationalized per the task sheet as
any closed trade with profit_ratio < 0 (all exit reasons), on the same pair
and side. Backtesting Trade persistence access mirrors OPT9 P2
(Trade.get_trades_proxy(is_open=False) + python-side filters) — proven in
this repo's backtests.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.persistence import Trade

_OSS = Path(__file__).resolve().parents[2] / "user_data" / "strategies" / "oss"
if str(_OSS) not in sys.path:
    sys.path.insert(0, str(_OSS))

from AB_LevGrid import ARL_2x  # noqa: E402

logger = logging.getLogger(__name__)

# --- gate rule core: verbatim from research_chop/scripts/regime_label.py ---
THR = 1.25          # mom_z +/- threshold (state rule core, no tuning)
TURB_RANK = 0.90    # atr_pct_rank turbulent overlay threshold
G4_WINDOW = 240     # trailing hours for the g4 directionlessness fraction
G4_FRAC = 0.90      # g4 fraction threshold
TAIL_ROWS = 800     # >= 720 (rank window) + slack; trailing -> tail == full


def _label_tail(df: pd.DataFrame) -> tuple[bool, bool, bool]:
    """(g1, g2, g4) at the LAST row of df; NaN-warmup -> False (gate OFF)."""
    close, high, low = df["close"], df["high"], df["low"]
    logc = np.log(close)
    ret_1h = logc.diff()
    vol_12h = ret_1h.rolling(12).std()
    mom_72h = logc.diff(72)
    mom_z = (mom_72h / (vol_12h * np.sqrt(72))).to_numpy()
    prev_close = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr_pct = (tr.rolling(14).mean() / close)
    atr_pct_rank = atr_pct.rolling(720, min_periods=240).rank(pct=True).to_numpy()

    g1 = np.abs(mom_z) < THR
    g1 = np.where(np.isnan(mom_z), False, g1)
    turb = atr_pct_rank >= TURB_RANK
    g2 = g1 & np.where(np.isnan(atr_pct_rank), False, turb)
    g1s = pd.Series(np.where(np.isnan(mom_z), np.nan,
                             (np.abs(mom_z) < THR).astype(float)))
    g4 = (g1s.rolling(G4_WINDOW, min_periods=G4_WINDOW).mean() >= G4_FRAC)
    return (bool(g1[-1]), bool(g2[-1]),
            bool(g4.iloc[-1]) if not pd.isna(g4.iloc[-1]) else False)


# ---------------------------------------------------------------------------
# market-gate arms (custom_stake_amount halving only)
# ---------------------------------------------------------------------------
class R3_Base(ARL_2x):
    """Shared causal market-gate machinery (not run directly)."""
    GATE_KIND = "g1"
    GATE_RISK = 0.5

    # (pair, idx-of-last-closed-candle) -> (g1, g2, g4); per-process cache
    _gate_row_cache: dict = {}

    def _gate_state(self, pair: str, current_time: datetime) -> tuple[bool, bool, bool]:
        if self.dp is None:
            return (False, False, False)
        df = self.dp.get_pair_dataframe(pair, self.timeframe)
        if df is None or len(df) == 0:
            return (False, False, False)
        ts = pd.Timestamp(current_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        idx = int(df["date"].searchsorted(ts.floor("ms"))) - 1   # strictly before
        if idx < 90:        # < 84 rows -> mom_z undefined -> no signal
            return (False, False, False)
        key = (pair, idx)
        hit = self._gate_row_cache.get(key)
        if hit is not None:
            return hit
        tail = df.iloc[max(0, idx - TAIL_ROWS): idx + 1]
        res = _label_tail(tail)
        self._gate_row_cache[key] = res
        return res

    def _market_gate_on(self, pair: str, current_time: datetime) -> bool:
        g1, g2, g4 = self._gate_state(pair, current_time)
        return {"g1": g1, "g2": g2, "g4": g4}[self.GATE_KIND]

    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        stake = super().custom_stake_amount(pair, current_time, current_rate,
                                            proposed_stake, min_stake, max_stake,
                                            leverage, entry_tag, side, **kwargs)
        if stake:
            try:
                if self._market_gate_on(pair, current_time):
                    stake = stake * float(self.GATE_RISK)
                    if max_stake:
                        stake = min(stake, max_stake)
                    if min_stake is not None:
                        stake = max(stake, min_stake)
            except Exception:
                logger.warning("R3 gate eval failed for %s at %s: stake "
                               "passed through unhalved", pair, current_time)
        return stake


class R3_G1h(R3_Base):
    """Negative control: |mom_z| < 1.25 (non-discriminating; ~73-75% of hours
    in BOTH regimes — PRE §2.1). Expected ~ uniform risk x 0.5."""
    GATE_KIND = "g1"


class R3_G2h(R3_Base):
    """Violent crash-adjacent chop: g1 AND atr_pct_rank >= 0.90."""
    GATE_KIND = "g2"


class R3_G4h(R3_Base):
    """Persistent directionlessness: >= 90% of the trailing 240 h had g1."""
    GATE_KIND = "g4"


# ---------------------------------------------------------------------------
# G3 failure-cluster arms (MAIN hypothesis)
# ---------------------------------------------------------------------------
class R3_C3_Base(ARL_2x):
    CLUSTER_N = 2          # >= N losing closes ...
    CLUSTER_D = 14         # ... within D days, same (pair, side)
    PAUSE_DAYS = 7         # C3p: block the side this long from the last loser

    def _side_closed_trades(self, pair: str, is_short: bool) -> list:
        """Closed trades of this pair+side (OPT9 P2 data-access idiom)."""
        try:
            closed = Trade.get_trades_proxy(is_open=False)
        except Exception:
            return []
        return [t for t in closed
                if t.pair == pair and t.is_short == is_short
                and t.close_date_utc is not None]

    @staticmethod
    def _last_winner_date(side_trades: list):
        wins = [t.close_date_utc for t in side_trades
                if (t.close_profit or 0.0) >= 0.0]
        return max(wins) if wins else None


class R3_C3h(R3_C3_Base):
    """Halving arm: state recomputed at every entry — losers on (pair, side)
    within the last D days, counted after the side's most recent profitable
    close; >= N -> stake x 0.5."""

    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        stake = super().custom_stake_amount(pair, current_time, current_rate,
                                            proposed_stake, min_stake, max_stake,
                                            leverage, entry_tag, side, **kwargs)
        if stake:
            try:
                if self._cluster_hot(pair, side == "short", current_time):
                    stake = stake * 0.5
                    if max_stake:
                        stake = min(stake, max_stake)
                    if min_stake is not None:
                        stake = max(stake, min_stake)
            except Exception:
                logger.warning("R3 C3h eval failed for %s at %s: stake "
                               "passed through unhalved", pair, current_time)
        return stake

    def _cluster_hot(self, pair: str, is_short: bool, now: datetime) -> bool:
        side = self._side_closed_trades(pair, is_short)
        if not side:
            return False
        since = now - timedelta(days=int(self.CLUSTER_D))
        last_win = self._last_winner_date(side)
        n = sum(1 for t in side
                if (t.close_profit or 0.0) < 0.0
                and t.close_date_utc >= since
                and (last_win is None or t.close_date_utc > last_win))
        return n >= int(self.CLUSTER_N)


class R3_C3p(R3_C3_Base):
    """Pause arm: D-day loser cluster ending at the most recent loser reaches
    N -> block NEW entries on that (pair, side) for PAUSE_DAYS from that loser
    (time unlock; a profitable close on the side after the last loser lifts
    the pause early). Parent P2 circuit preserved via super()."""

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str,
                            current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        if not super().confirm_trade_entry(pair, order_type, amount, rate,
                                           time_in_force, current_time, entry_tag,
                                           side, **kwargs):
            return False
        try:
            if self._side_paused(pair, side == "short", current_time):
                return False
        except Exception:
            logger.warning("R3 C3p eval failed for %s at %s: entry allowed",
                           pair, current_time)
        return True

    def _side_paused(self, pair: str, is_short: bool, now: datetime) -> bool:
        side = self._side_closed_trades(pair, is_short)
        losers = [t for t in side if (t.close_profit or 0.0) < 0.0]
        if not losers:
            return False
        last_stop = max(t.close_date_utc for t in losers)
        if now - last_stop >= timedelta(days=int(self.PAUSE_DAYS)):
            return False                       # time unlock
        last_win = self._last_winner_date(side)
        if last_win is not None and last_win > last_stop:
            return False                       # profitable close lifted pause
        since_cluster = last_stop - timedelta(days=int(self.CLUSTER_D))
        cluster_n = sum(1 for t in losers if since_cluster <= t.close_date_utc <= last_stop)
        return cluster_n >= int(self.CLUSTER_N)


# --- pre-registered IS grid N x D (PRE §2: N in {2,3,4} x D in {14,30}) -----
class R3_C3h_N2_D14(R3_C3h):
    CLUSTER_N = 2
    CLUSTER_D = 14


class R3_C3h_N2_D30(R3_C3h):
    CLUSTER_N = 2
    CLUSTER_D = 30


class R3_C3h_N3_D14(R3_C3h):
    CLUSTER_N = 3
    CLUSTER_D = 14


class R3_C3h_N3_D30(R3_C3h):
    CLUSTER_N = 3
    CLUSTER_D = 30


class R3_C3h_N4_D14(R3_C3h):
    CLUSTER_N = 4
    CLUSTER_D = 14


class R3_C3h_N4_D30(R3_C3h):
    CLUSTER_N = 4
    CLUSTER_D = 30


# pause arm: run ONLY at the IS-best N/D point (disclosed compute-saving rule)
class R3_C3p_N2_D14(R3_C3p):
    CLUSTER_N = 2
    CLUSTER_D = 14


class R3_C3p_N2_D30(R3_C3p):
    CLUSTER_N = 2
    CLUSTER_D = 30


class R3_C3p_N3_D14(R3_C3p):
    CLUSTER_N = 3
    CLUSTER_D = 14


class R3_C3p_N3_D30(R3_C3p):
    CLUSTER_N = 3
    CLUSTER_D = 30


class R3_C3p_N4_D14(R3_C3p):
    CLUSTER_N = 4
    CLUSTER_D = 14


class R3_C3p_N4_D30(R3_C3p):
    CLUSTER_N = 4
    CLUSTER_D = 30
