"""OPT3_MomRegime15mLb21 — Phase-3 final drawdown governance of the Phase-2 winner.

Phase-2 final (OPT2_MomRegime15mLb21, mpw45/tolm3/abs re-applied at that file's
bottom; IS 20210101-20230101, 12 coins): 52 trades / +590.93% / maxDD 16.81% /
Sharpe 0.31 / PF 2.18 / funding -11,307 USDT.  Profit is still concentrated in
2021.  Phase-3 goal: push IS maxDD toward <= 12% and improve half-window
balance while keeping IS profit >= +450% (76% of the phase-2 final).

Two NEW, independent SIZING levers (both default OFF => this class with both
levers off is sizing-identical to the phase-2 final; signals untouched):

  1. VOL_TARGET_ENABLE — per-coin volatility targeting:
       target_i = (PV / TOP_N) * min(1, vol_ref / vol_i)
     vol_i  = coin's 30-day realized vol = std of DAILY close log-returns;
     vol_ref = cross-sectional MEDIAN of vol_i across the whitelist that day.
     Above-median-vol coins are scaled DOWN proportionally; below-median coins
     are NOT scaled up (min(1, .)).  Because the scale is <= 1, the scaled
     target stays <= PV/TOP_N < MAX_POSITION_WEIGHT — the structural red line
     (any mpw must stay > 1/TOP_N = 0.333; 0.45 is inherited untouched).

  2. TRANSITION_BAND_ENABLE — regime transition-band half sizing:
       while btc_known in [sma*(1-tol), sma*(1-tol+width)) the target halves.

CAUSALITY GUARANTEES (both levers):
  * All inputs come from the SAME `known` daily panel the frozen phase-1/2
    code already uses: raw daily feather closes shifted one full day
    (`Pd.shift(1)`), so at any intraday decision only closes through
    YESTERDAY are visible.  vol_i additionally shifts implicitly: its returns
    are the returns OF the known panel, i.e. they end at yesterday's close.
  * The per-candle lookup is a backward as-of search (searchsorted side=
    "right" - 1) on the daily index: a 15m candle at t can only pick the
    daily row dated <= t, whose inputs were final at that row's midnight.
  * The band's sma is `btc_known.rolling(REGIME_SMA).mean()` — the EXACT
    series the inherited regime formula compares against — so band membership
    and the regime flip can never disagree on inputs (no mixed references).

ANCHORING DISCLOSURE (transition band, one deliberate deviation):
  The inherited regime is `ron = btc_known > sma * (1 - REGIME_TOLERANCE)`
  (tol = -0.03 => risk-on requires btc >= 3% ABOVE sma100, cf. OPT2 docstring).
  The task text's worked example "[sma*(1+tol), sma*(1+tol+0.05)) = [sma*0.97,
  sma*1.02)" is provably INERT under this code: any candle where a target is
  computed has hold=True, which already implies btc_known > sma*1.03 — disjoint
  from [0.97, 1.02).  The stated intent is "刚进入 risk-on 的不稳区" (the
  unstable zone JUST after entering risk-on), so the band is anchored at the
  ACTUAL risk-on threshold: [sma*(1-tol), sma*(1-tol+0.05)) = [1.03, 1.08) for
  tol = -0.03.  The literal [0.97, 1.02) variant is therefore NOT run as a
  separate cell — it is mathematically identical to `base` by construction.

  Mid-hold semantics: a halved target stops ACCUMULATION and halves the size
  of any FRESH entry made while in-band; an existing position already above
  the halved target is not force-trimmed (only the MAX_POSITION_WEIGHT cap
  trims, exactly as in phase 2).  Same for vol-targeting: targets only gate
  accumulation, they never force-sell.

Both levers act ONLY at the two sizing points (custom_stake_amount and the
accumulation branch of adjust_trade_position, both copied verbatim from the
parent with the single marked delta).  Entries/exits/ranking/hysteresis/
funding gate / liquidity caps are inherited verbatim from OPT2_MomRegime15mLb21.

NaN policy: a coin without 30 known daily closes (all non-BTC/ETH/SOL coins
during January 2021 — their feathers start 2021-01-01) has NaN vol -> scale
1.0, mirroring the NaN-passes convention of the funding gate.  NaN sma/btc
(warm-up) -> never in band -> scale 1.0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame

from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class OPT3_MomRegime15mLb21(OPT2_MomRegime15mLb21):
    # --- phase-3 levers (defaults OFF => sizing-identical to the phase-2 final) ---
    VOL_TARGET_ENABLE = False
    VOL_WINDOW_DAYS = 30           # daily log-return std window for vol_i
    TRANSITION_BAND_ENABLE = False
    TRANSITION_BAND_WIDTH = 0.05   # band width ABOVE the actual risk-on threshold

    _scale = None        # cached daily size-scale panel (rows=days, cols=pairs)
    _scale_key = None    # cache key: (asof, whitelist, lever params)

    # ------------------------------------------------------------------
    # phase-3 sizing scale
    # ------------------------------------------------------------------
    def _scale_panel(self):
        """Daily per-pair size multiplier = vol_scale * band_scale.
        None when both levers are off (callers then use the 1.0 fast path)."""
        if not (self.VOL_TARGET_ENABLE or self.TRANSITION_BAND_ENABLE):
            return None
        wl = tuple(sorted(self.dp.current_whitelist()))
        ref = self.dp.get_pair_dataframe(self.REGIME_REF, self.timeframe)
        asof = ref["date"].iloc[-1] if ref is not None and len(ref) else None
        key = (asof, wl, bool(self.VOL_TARGET_ENABLE), int(self.VOL_WINDOW_DAYS),
               bool(self.TRANSITION_BAND_ENABLE), float(self.TRANSITION_BAND_WIDTH))
        if self._scale is not None and self._scale_key == key:
            return self._scale

        Pd = self._daily_closes(wl)
        known = Pd.shift(1)     # yesterday's close, known intraday (inherited convention)
        scale = DataFrame(1.0, index=Pd.index, columns=Pd.columns)

        if self.VOL_TARGET_ENABLE:
            # returns OF the known panel: lk at daily row d uses closes d-1, d-2;
            # the 30-return window at row d therefore uses closes d-30 .. d-1 —
            # every input final before day d's midnight => strictly causal.
            lk = np.log(known / known.shift(1))
            vol = lk.rolling(int(self.VOL_WINDOW_DAYS),
                             min_periods=int(self.VOL_WINDOW_DAYS)).std()
            vol_ref = vol.median(axis=1)               # cross-sectional median (skipna)
            # rdiv(..., axis=0) = vol_ref / vol_i aligned on DATES.  NB: a bare
            # `vol_ref / vol` (Series/DataFrame) would align on the DataFrame's
            # COLUMNS instead (dates vs pair names -> all-NaN outer join) — the
            # explicit axis is load-bearing; caught by the offline sanity check.
            vt = vol.rdiv(vol_ref, axis=0).clip(upper=1.0)   # calm coins stay at 1.0
            scale = scale * vt.fillna(1.0)             # NaN (warm-up/young) -> 1.0

        if self.TRANSITION_BAND_ENABLE:
            btc = known.get(self.REGIME_REF)
            if btc is not None:
                sma = btc.rolling(self.REGIME_SMA).mean()   # same sma as the regime formula
                thr = 1.0 - self.REGIME_TOLERANCE           # actual risk-on multiple (1.03)
                in_band = (btc >= sma * thr) & (btc < sma * (thr + self.TRANSITION_BAND_WIDTH))
                tb = pd.Series(1.0, index=Pd.index).where(~in_band, 0.5)  # NaN -> not in band
                scale = scale.mul(tb, axis=0)

        self._scale = scale
        self._scale_key = key
        return scale

    def _size_scale(self, pair: str, ts) -> float:
        """Backward as-of multiplier for `pair` at 15m timestamp `ts`; 1.0 fast path."""
        if not (self.VOL_TARGET_ENABLE or self.TRANSITION_BAND_ENABLE):
            return 1.0
        panel = self._scale_panel()
        if panel is None or pair not in panel.columns:
            return 1.0
        s = panel[pair]
        i = s.index.searchsorted(pd.Timestamp(ts), side="right") - 1
        if i < 0:
            return 1.0
        v = float(s.iloc[i])
        return v if v == v else 1.0    # NaN guard (defensive; panel is already filled)

    # ------------------------------------------------------------------
    # Sizing point 1: OPT1 custom_stake_amount, verbatim EXCEPT the marked delta.
    # ------------------------------------------------------------------
    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        if self.dp.runmode.value in ("plot", "other"):
            return proposed_stake
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        ts = df["date"].iloc[-1] if df is not None and len(df) else current_time
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        target = self._portfolio_value() / self.TOP_N
        target *= self._size_scale(pair, ts)                     # <-- phase-3 delta
        stake = min(proposed_stake, target, fillable, max_stake)
        if min_stake and stake < min_stake:
            return 0.0
        return max(stake, 0.0)

    # ------------------------------------------------------------------
    # Sizing point 2: OPT2 adjust_trade_position, verbatim EXCEPT the marked delta.
    # ------------------------------------------------------------------
    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit, **kwargs):
        if self.dp.runmode.value in ("plot", "other"):
            return None
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or len(df) == 0:
            return None
        last = df.iloc[-1].squeeze()
        pv = self._portfolio_value()
        current_value = trade.amount * current_rate
        # max-position-weight cap: trim a runaway winner first (banks profit into cash)
        if self.MAX_POSITION_WEIGHT and pv > 0 and current_value > self.MAX_POSITION_WEIGHT * pv:
            trim = self.MAX_POSITION_WEIGHT * pv - current_value   # negative => reduce
            if not min_stake or abs(trim) >= min_stake:
                return trim
        if not bool(last["hold"]):
            if not self.EXIT_LIQUIDITY_CAP:
                return None   # leaving the basket -> full exit handled by the exit signal
            # Liquidity-capped unwind: release only what this candle can absorb.
            sellable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
            if sellable <= 0 or sellable >= current_value:
                return None
            reduce = -min(sellable, current_value)
            if min_stake and abs(reduce) < min_stake:
                return None
            return reduce
        # OPT2 funding gate on ACCUMULATION adds (mode-aware; NaN = no data -> allow).
        # Trim/exit paths above are deliberately NOT gated (same as phase 1/2).
        fr = last.get("funding_rate")
        if self.FUNDING_GATE_MODE == "q80":
            thr = last.get("funding_gate_thr")
            if pd.notna(fr) and pd.notna(thr) and float(fr) > float(thr):
                return None
        else:
            if pd.notna(fr) and float(fr) > self.funding_max:
                return None
        target = pv / self.TOP_N
        target *= self._size_scale(trade.pair, df["date"].iloc[-1])   # <-- phase-3 delta
        if current_value >= target * 0.98:
            return None   # already at (scaled) target weight
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        add = min(target - current_value, fillable, max_stake)
        if add <= 0 or (min_stake and add < min_stake):
            return None
        return add
