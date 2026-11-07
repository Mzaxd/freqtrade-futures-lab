"""LVG line 2 — B-sleeve leverage ladder + vol-targeted leverage (2026-11-07).

B (OPT2_MomRegime15mLb21, frozen) sizes notional to equity/TOP_N via
adjust_trade_position; the leverage() callback is therefore the true PnL
exposure dial (margin = notional/lev, PnL scales with lev). Known from the
earlier leverage map: 2x sweet spot (21-26 +29481% / DD 26.9% / 0 liq),
5x kill-lined. Pre-registered cells (research_improve/lvg/pre_reg.md):

  LVG_B_15x  fixed 1.5x
  LVG_B_2x   fixed 2.0x
  LVG_B_2xvt lev_t = clamp(2.0 * 60.6/RV30_t, 1.0, 2.5)

RV30_t (same math as line 1): annualized stdev of the last 30 log returns
of FULLY CLOSED BTC daily candles (days D-30..D-1 while now is in day D —
strictly causal). Data source: BTC 1d feather read directly from disk, the
same source B's own regime panel uses (_daily_closes); the loaded series is
cached once (static file) and sliced as-of every call. Warmup (<31 closed
days) -> base leverage 2.0 without the vol adjustment (neutral m=1).

Leverage is an ENTRY-time property in freqtrade: open positions keep their
entry leverage; the overlay only changes new entries.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import pandas as pd

from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class LVG_B_Lev(OPT2_MomRegime15mLb21):
    LVG_BASE = 2.0
    LVG_TARGET = 60.6     # annualized %, IS 21-23 median RV30
    LVG_LO = 1.0
    LVG_HI = 2.5

    _btc_daily: pd.Series | None = None   # static cache (file data)

    def _btc_daily_closes(self) -> pd.Series | None:
        if LVG_B_Lev._btc_daily is not None:
            return LVG_B_Lev._btc_daily
        f = (Path(__file__).resolve().parents[2] / "data" / "binance" / "futures"
             / "BTC_USDT_USDT-1d-futures.feather")
        if not f.exists():
            return None
        d = pd.read_feather(f)
        s = d.set_index(pd.DatetimeIndex(pd.to_datetime(d["date"], utc=True)))["close"]
        LVG_B_Lev._btc_daily = s.sort_index()
        return LVG_B_Lev._btc_daily

    def _rv30_pct(self, current_time: datetime) -> float | None:
        s = self._btc_daily_closes()
        if s is None or len(s) < 31:
            return None
        ts = pd.Timestamp(current_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        day0 = ts.floor("1D")
        closed = s[s.index < day0]          # days D-1 and earlier (fully closed)
        if len(closed) < 31:
            return None
        rets = closed.iloc[-31:]
        lr = [math.log(rets.iloc[i] / rets.iloc[i - 1]) for i in range(1, 31)]
        mu = sum(lr) / 30.0
        var = sum((x - mu) ** 2 for x in lr) / 29.0
        return math.sqrt(var) * math.sqrt(365.0) * 100.0

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return min(float(self.LVG_BASE), max_leverage)


class LVG_B_15x(LVG_B_Lev):
    LVG_BASE = 1.5


class LVG_B_2x(LVG_B_Lev):
    LVG_BASE = 2.0


class LVG_B_2xvt(LVG_B_Lev):
    LVG_BASE = 2.0
    LVG_TARGET = 60.6
    LVG_LO = 1.0
    LVG_HI = 2.5

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        rv = self._rv30_pct(current_time)
        if rv is None or rv <= 0:
            lev = float(self.LVG_BASE)
        else:
            lev = float(self.LVG_BASE) * float(self.LVG_TARGET) / rv
            lev = min(max(lev, float(self.LVG_LO)), float(self.LVG_HI))
        return min(lev, max_leverage)
