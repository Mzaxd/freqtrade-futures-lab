"""crash_overlay — CRASH line de-risk overlays on sleeve A (2026-11-07).

Pre-registration: research_improve/crash/pre_reg.md (written BEFORE any 24-26
variant evaluation). All variants subclass ARL_2x (frozen A sleeve: OPT9_Recycle
RECYCLE_MULT=1.21 + lev2 + P2 cluster circuit) and change EXACTLY ONE thing:
the per-ENTRY risk multiplier via OPT9_VolatilitySystem's `_risk_fraction`
hook (V3 instead gates `confirm_trade_entry`, keeping the P2 circuit).

Structural rationale (vs the two falsified traps, research_chop):
  * acts on POSITION SIZE, not an on/off gate -> no per-day selectivity needed;
    if the state window overlaps the bleed, exposure (and bleed) scales down
    proportionally;
  * not the sparse G3 self-referential gate: the armed states here (RV spike /
    sleeve drawdown) persist for weeks in post-crash chop, not 8/207 trades.

RV30 (frozen definition, diag_rv_is.py): annualized std of the last 720 hourly
BTC log-returns, sampled at the LAST hour of each fully-closed UTC day. The
strategy reads the BTC 1h feather directly from disk (B-family `_daily_closes`
convention) so full history is available regardless of backtest timerange, and
every lookup uses ONLY days strictly closed before current_time (causal).

Knobs frozen from the 2021-23 IS sample (never tuned on 24-26):
  RV_FROZEN_THRESHOLD = 0.850  (pooled 21-23 p85 of daily RV30)
  RV_RANK_WINDOW_D = 365, RV_RANK_Q = 0.85  (trailing self-percentile)
  DD_ARM = 0.92  (IS cost: only 4.0% of days below 0.92x running peak)
  DD_REARM = 0.97 (hysteresis band; recovery re-arms before a new high)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from AB_LevGrid import ARL_2x

FEATHER = Path(__file__).resolve().parents[2] / "data" / "binance" / "futures" / "BTC_USDT_USDT-1h-futures.feather"


class CrashBase(ARL_2x):
    """RV plumbing + inert factor defaults (1.0 = byte-identical sizing)."""

    RV_WINDOW_H = 720
    RV_FROZEN_THRESHOLD = 0.850   # 21-23 pooled p85 (rv_is_stats.json)
    RV_RANK_WINDOW_D = 365
    RV_RANK_Q = 0.85
    DD_ARM = 0.92
    DD_REARM = 0.97
    DD_FACTOR = 0.5

    _rv_cache = None              # (days, values, frozen_active, rank_active)
    _dd_peak: float | None = None
    _dd_armed: bool = False

    # ------------------------------------------------------------------ RV
    def _rv_series(self):
        if self._rv_cache is not None:
            return self._rv_cache
        df = pd.read_feather(FEATHER)[["date", "close"]]
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.sort_values("date").reset_index(drop=True)
        rv_h = np.log(df["close"].astype(float)).diff().rolling(self.RV_WINDOW_H).std() * np.sqrt(24 * 365)
        frame = pd.DataFrame({"date": df["date"], "rv": rv_h}).dropna()
        frame["day"] = frame["date"].dt.floor("1D")
        daily = frame.groupby("day")["rv"].last()   # 23:00 sample = day closed
        vals = daily.to_numpy(dtype=float)
        days = pd.DatetimeIndex(daily.index)
        rank_active = np.zeros(len(vals), dtype=bool)
        for i in range(len(vals)):
            if i + 1 < self.RV_RANK_WINDOW_D:
                continue
            w = vals[i + 1 - self.RV_RANK_WINDOW_D: i + 1]
            rank_active[i] = vals[i] >= np.quantile(w, self.RV_RANK_Q)
        frozen_active = vals > self.RV_FROZEN_THRESHOLD
        self._rv_cache = (days, vals, frozen_active, rank_active)
        return self._rv_cache

    def _rv_state(self, current_time: datetime) -> tuple[bool, bool]:
        """(frozen_active, rank_active) for the last FULLY CLOSED UTC day."""
        days, _vals, frozen_active, rank_active = self._rv_series()
        ts = pd.Timestamp(current_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        pos = int(days.searchsorted(ts.floor("1D"), side="right")) - 1
        while pos >= 0 and (days[pos] + pd.Timedelta(days=1)) > ts:
            pos -= 1          # day pos not fully closed at ts
        if pos < 0:
            return (False, False)
        return (bool(frozen_active[pos]), bool(rank_active[pos]))

    # ------------------------------------------------------------------ factors
    def _rv_rank_factor(self, current_time: datetime) -> float:
        return 0.5 if self._rv_state(current_time)[1] else 1.0

    def _dd_factor(self) -> float:
        """Sleeve drawdown band with hysteresis; peak starts at run start
        (fresh-instance deployment semantics, disclosed in pre_reg §6.3)."""
        eq = float(self.wallets.get_total_stake_amount())
        if self._dd_peak is None:
            self._dd_peak = eq
            return 1.0
        self._dd_peak = max(self._dd_peak, eq)
        if not self._dd_armed and eq < self.DD_ARM * self._dd_peak:
            self._dd_armed = True
        elif self._dd_armed and eq >= self.DD_REARM * self._dd_peak:
            self._dd_armed = False
        return self.DD_FACTOR if self._dd_armed else 1.0


# --- pre-registered variants (pre_reg.md §3) --------------------------------
class crash_RVfroz(CrashBase):
    """V1: RV30 above frozen 21-23 pooled p85 (0.850) -> new-entry risk x0.5."""
    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        return 0.5 if self._rv_state(current_time)[0] else 1.0


class crash_RVrank(CrashBase):
    """V2: RV30 above its own trailing-365d p85 -> new-entry risk x0.5."""
    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        return self._rv_rank_factor(current_time)


class crash_RVpause(CrashBase):
    """V3: same RV signal as V2 but a binary PAUSE of new entries (structural
    control: size-scaling vs gate). P2 cluster circuit evaluated first."""
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        if not super().confirm_trade_entry(pair, order_type, amount, rate, time_in_force,
                                           current_time, entry_tag, side, **kwargs):
            return False
        return not self._rv_state(current_time)[1]


class crash_DDband(CrashBase):
    """V4: sleeve equity < 0.92x running peak -> risk x0.5 until >= 0.97x peak."""
    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        return self._dd_factor()


class crash_RV_DD(crash_RVrank):
    """V5: V2 x V4 multiplicative, floor 0.25."""
    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        f = super()._risk_fraction(side, current_time) * self._dd_factor()
        return max(f, 0.25)


class crash_DDband65(crash_DDband):
    """V6: V4 structure at dose 0.65 (dose-response control)."""
    DD_FACTOR = 0.65
