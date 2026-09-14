"""OPT2_MomRegime15mLb21 — Phase-2 drawdown governance of the Phase-1 winner.

Phase-1 baseline (OPT1_MomRegime15mLb21, IS 20210101-20230101, 12 coins):
+542.50% / maxDD 36.03% / Sharpe 0.29 / PF 1.84 / funding -11,828 USDT.
Profit was all 2021 (+82.5k); 2022 gave back -28.3k.  Phase-2 goal: maxDD
<= 25% while keeping most of the profit.  This file exposes exactly three
knobs as class attributes so the 2x2x2 grid subclasses only re-set them:

  1. MAX_POSITION_WEIGHT (0.45 phase-1 value / 0.30 tighter grid cell):
     lower cap trims a runaway winner earlier and banks more cash — the
     direct per-position drawdown lever.
  2. REGIME_TOLERANCE (0.0 phase-1 value / -0.03 tighter grid cell):
     unchanged semantics in the parent — risk-on requires
     btc > sma100 * (1 - tol), so tol=-0.03 demands BTC be >= 3% ABOVE its
     SMA100 before the basket may hold (fewer marginal regime flips).
  3. FUNDING_GATE_MODE in {"abs", "q80"}:
       "abs"  -> Phase-1 behavior, signal-identical to OPT1_MomRegime15mLb21:
                 block long entries / accumulation adds while the causal
                 settled funding_rate > funding_max (fixed 0.0005 / 8h).
       "q80"  -> REPLACES the absolute threshold: block entries/adds while
                 funding_rate > its own per-pair rolling 30-day 80th
                 percentile.  Computed in populate_indicators on the causal
                 `funding_rate` column from opt_common.attach_funding (which
                 is already lagged one full settlement), trailing window,
                 then .shift(1) so the current row can never set its own bar.
                 NaN threshold (warm-up / no funding data) or NaN rate ->
                 allow, mirroring the NaN-passes rule of the abs gate.

Grid subclasses (files OPT2_MomRegime15mLb21_<tag>.py) only change the three
attributes above.  Nothing else differs from OPT1_MomRegime15mLb21: the
cross-sectional ranking, hysteresis, exits, liquidity caps and trim logic are
inherited verbatim; adjust_trade_position is copied verbatim EXCEPT the
mode-aware funding check on the accumulation branch (documented inline).

This file's own defaults = the phase-1 winner (mpw45 / tol0 / abs), i.e. the
grid origin, so any single-dimension delta is attributable by diff.  After
the pre-registered grid selection the FINAL candidate's parameters are
re-applied to this class at the bottom of the file so that this file IS the
phase-2 deliverable strategy.
"""
from __future__ import annotations

import pandas as pd
from pandas import DataFrame
from freqtrade.persistence import Trade

import opt_common

from OPT1_MomRegime15mLb21 import OPT1_MomRegime15mLb21


class OPT2_MomRegime15mLb21(OPT1_MomRegime15mLb21):
    # --- phase-2 knobs (defaults = phase-1 winner = grid origin mpw45/tol0/abs;
    #     the winning cell's values are re-applied at the bottom of this file
    #     once the pre-registered grid selection has been made) ---
    MAX_POSITION_WEIGHT = 0.45   # {0.45, 0.30} grid dim 1
    REGIME_TOLERANCE = 0.0       # {0.0, -0.03} grid dim 2  (ron = btc > sma*(1-tol))
    FUNDING_GATE_MODE = "abs"    # {"abs", "q80"} grid dim 3

    # --- q80 gate parameters (only used when FUNDING_GATE_MODE == "q80") ---
    FUNDING_Q80_WINDOW_DAYS = 30
    FUNDING_Q80_QUANTILE = 0.8
    FUNDING_Q80_MIN_PERIODS_DAYS = 3   # require >= 3 days of rate history in-window

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        # attach_funding already ran in super(); add the causal rolling
        # threshold column.  15m frame -> 96 rows/day.  min_periods keeps the
        # first days NaN (-> gate open) until enough settled rates exist.
        if self.FUNDING_GATE_MODE == "q80":
            win = int(self.FUNDING_Q80_WINDOW_DAYS) * 96
            mp = int(self.FUNDING_Q80_MIN_PERIODS_DAYS) * 96
            dataframe["funding_gate_thr"] = (
                dataframe["funding_rate"]
                .rolling(win, min_periods=mp)
                .quantile(self.FUNDING_Q80_QUANTILE)
                .shift(1)
            )
        else:
            dataframe["funding_gate_thr"] = float("nan")
        return dataframe

    def _funding_entry_ok(self, dataframe: DataFrame) -> pd.Series:
        """Vectorized long-entry funding gate, mode-aware. True = allowed."""
        fr = dataframe["funding_rate"]
        if self.FUNDING_GATE_MODE == "q80":
            thr = dataframe["funding_gate_thr"]
            return fr.isna() | thr.isna() | (fr <= thr)
        return opt_common.funding_gate_long(dataframe, self.funding_max)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["hold"]
            & (dataframe["volume"] > 0)
            & self._funding_entry_ok(dataframe),
            "enter_long",
        ] = 1
        return dataframe

    # --- verbatim copy of OPT1_MomRegime15mFast.adjust_trade_position with the
    #     ONLY delta at the accumulation funding check (mode-aware). ---
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
        # Trim/exit paths above are deliberately NOT gated (same as phase 1).
        fr = last.get("funding_rate")
        if self.FUNDING_GATE_MODE == "q80":
            thr = last.get("funding_gate_thr")
            if pd.notna(fr) and pd.notna(thr) and float(fr) > float(thr):
                return None
        else:
            if pd.notna(fr) and float(fr) > self.funding_max:
                return None
        target = pv / self.TOP_N
        if current_value >= target * 0.98:
            return None   # already at target weight
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        add = min(target - current_value, fillable, max_stake)
        if add <= 0 or (min_stake and add < min_stake):
            return None
        return add


# === FINAL CANDIDATE (pre-registered grid selection, 2026-09-12) ===
# Grid (8 cells, IS 20210101-20230101, 12 coins; summary_opt2_mom_grid.csv):
#   winner mpw45_tolm3_abs — profit floor >= +325% met by 8/8, lowest maxDD among them.
#   +590.93% / maxDD 16.81% / Sharpe 0.31 / PF 2.18 / 52 trades / funding -11,307.
#   Grid origin mpw45_tol0_abs reproduced phase-1 OPT1 exactly (60 trades,
#   +542.50%, DD 36.03%) — implementation cross-check.
OPT2_MomRegime15mLb21.MAX_POSITION_WEIGHT = 0.45
OPT2_MomRegime15mLb21.REGIME_TOLERANCE = -0.03
OPT2_MomRegime15mLb21.FUNDING_GATE_MODE = "abs"
