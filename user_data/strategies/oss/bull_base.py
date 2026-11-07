"""bull_base — BULL sleeve research: structural re-entry fixes for frozen B
(OPT2_MomRegime15mLb21), pre-registered in research_improve/bull/pre_reg.md.

Hypothesis (diagnostic-backed): B's 2023 shortfall (+44% vs market +150.8%) is
dominated by the bear-to-bull RE-ENTRY lag of the BTC regime gate
(SMA100x1.03): the gate opened 2023-01-13 with the 3-coin basket already
+41.4% off the Jan-1 level (SOL +83%).  On the 3-coin universe the 14d
momentum rank is degenerate (rank<=TOP_N always true) and the liquidity ramp
is a non-factor at 3000-wallet size, so the gate structure is THE lever.

This file adds three MECHANISM knobs (no re-tuning of frozen parameters):

  FAST_ENABLE / FAST_DEPRIVATION_DAYS(250) / FAST_SMA(50) / FAST_SCALE
      Deep-bear fast re-entry channel.  dep[t] = trading days since the last
      standard risk-on day (BTC_known > SMA100_known x (1-tol)).  When
      dep >= 250 AND BTC_known > its SMA50, a latch opens a HALF (FAST_SCALE
      0.5) or FULL (1.0) sized basket while the standard gate is still off.
      The latch releases when BTC falls below its SMA50 or the standard gate
      turns on.  Rationale: 250d of regime deprivation separates
      "post-capitulation recovery" (2022-12/2023-01: fires 12-27 benignly,
      01-05 for the +41.4% January leg) from bear-market rallies (2022 Feb
      dep=66, Aug dep<=132, Oct-Nov dep<=213 — none reach 250).
      2021/2024/2025/2026 max dep = 78/51/81/188: the channel never fires
      there, so OOS behavior of this knob alone is frozen-identical.

  LADDER_ENABLE
      Dual-speed regime ladder (task variant a, falsification control):
      half basket while BTC_known in [SMA100, SMA100x(1-tol)), full above.
      Diagnostic prediction: net harm (2022 gap days basket sum -20.9%).

  INTRADAY_REGIME
      Evaluate the frozen threshold on the LIVE 15m BTC close against
      yesterday's SMA100 (kills the 1-day stale-close lag; every gate
      transition moves ~1 day earlier, both directions).

  COIN_FAST_SMA (None or 20)
      Asymmetric per-coin re-entry: while the standard regime is CONFIRMED
      (x1.03 satisfied), a coin may ENTER the basket above its SMA20;
      the STAY/exit trend gate stays SMA50.  (Coin-level analog of the
      fast-re-entry asymmetry; targets SOL's Mar-Jun 2023 whipsaw cost.)

Everything else (mpw 0.45, tol -0.03, abs funding gate, TOP_N=3, hourly
membership decisions, liquidity caps, trim logic) is inherited verbatim from
frozen B.  Sizing: when the regime is in a HALF state the per-coin target
weight becomes pv*0.5/TOP_N and positions are trimmed DOWN to that target
(only when scale<1 — at scale 1.0 the sizing path is byte-equivalent to
frozen B, so variants whose scale is always 1.0 while held cannot drift).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame

from OPT2_MomRegime15mLb21 import OPT2_MomRegime15mLb21


class BullBase(OPT2_MomRegime15mLb21):
    # --- pre-registered mechanism knobs (see module docstring / pre_reg.md) ---
    FAST_ENABLE = False
    FAST_DEPRIVATION_DAYS = 250
    FAST_SMA = 50
    FAST_SCALE = 0.5
    LADDER_ENABLE = False
    INTRADAY_REGIME = False
    COIN_FAST_SMA = None    # e.g. 20 -> asymmetric coin entry gate

    _scale_15 = None        # per-15m-row target scale, cached with _xs

    # ---------------------------------------------------------------
    def _xs_params(self) -> tuple:
        p = super()._xs_params()
        return p + (
            bool(self.FAST_ENABLE), int(self.FAST_DEPRIVATION_DAYS),
            int(self.FAST_SMA), float(self.FAST_SCALE),
            bool(self.LADDER_ENABLE), bool(self.INTRADAY_REGIME),
            None if self.COIN_FAST_SMA is None else int(self.COIN_FAST_SMA),
        )

    def _compute_xs(self) -> DataFrame:
        """Frozen parent's membership computation with the regime/trend gate
        block replaced by the scale-based structure.  Everything downstream
        (rank, hysteresis, hourly decisions) is verbatim frozen logic."""
        wl = tuple(sorted(self.dp.current_whitelist()))
        ref = self.dp.get_pair_dataframe(self.REGIME_REF, self.timeframe)
        asof = ref["date"].iloc[-1] if ref is not None and len(ref) else None
        key = (asof, wl) + self._xs_params()
        if self._xs is not None and self._xs_key == key:
            return self._xs

        # --- daily inputs (full history from disk), lagged 1 day (causal) ---
        Pd = self._daily_closes(wl)
        known = Pd.shift(1)
        ref90 = known.shift(self.MOM_LOOKBACK_DAYS)
        btc_d = known.get(self.REGIME_REF)

        # --- regime structure on the daily (causal) series ---
        tol_mult = 1.0 - self.REGIME_TOLERANCE          # frozen: 1.03
        sma100 = btc_d.rolling(self.REGIME_SMA).mean()
        std = (btc_d > sma100 * tol_mult).fillna(False)  # frozen risk-on
        if self.INTRADAY_REGIME or self.LADDER_ENABLE or self.FAST_ENABLE:
            sma_fast = btc_d.rolling(self.FAST_SMA).mean()
            above_fast = (btc_d > sma_fast).fillna(False)

        scale_d = pd.Series(0.0, index=Pd.index)
        std_idx = std[std].index
        scale_d.loc[std_idx] = 1.0

        if self.LADDER_ENABLE:
            above100 = (btc_d > sma100).fillna(False)
            scale_d.loc[above100[~std & above100].index] = 0.5

        if self.FAST_ENABLE:
            # deprivation: trading days since last standard-ON day
            pos = np.arange(len(std))
            last_on = pd.Series(np.where(std.to_numpy(), pos, np.nan),
                                index=std.index).ffill()
            dep = pd.Series(pos, index=std.index) - last_on
            dep = dep.fillna(pd.Series(pos, index=std.index))  # before first-ever ON: count from data start
            # fast latch: needs dep>=thr and above fast SMA; releases below
            # fast SMA or on standard ON (standard then governs).
            latch = np.zeros(len(std), dtype=bool)
            prev = False
            dep_v = dep.to_numpy()
            std_v = std.to_numpy()
            fast_v = above_fast.to_numpy()
            thr = int(self.FAST_DEPRIVATION_DAYS)
            for i in range(len(std)):
                if std_v[i]:
                    prev = False
                elif fast_v[i] and (prev or dep_v[i] >= thr):
                    prev = True
                else:
                    prev = False
                latch[i] = prev
            fast_mask = pd.Series(latch, index=std.index) & ~std
            scale_d.loc[fast_mask[fast_mask].index] = float(self.FAST_SCALE)

        # --- current 15m close panel (freqtrade-loaded) ---
        closes = {}
        for p in wl:
            df = self.dp.get_pair_dataframe(p, self.timeframe)
            if df is not None and len(df):
                s = df.copy(); s["date"] = pd.to_datetime(s["date"], utc=True)
                closes[p] = s.set_index("date")["close"]
        P15 = pd.DataFrame(closes).sort_index()

        # --- map daily structure onto the 15m index ---
        ref90_15 = ref90.reindex(columns=P15.columns).reindex(P15.index, method="ffill")
        if self.INTRADAY_REGIME:
            line15 = (sma100 * tol_mult).reindex(P15.index, method="ffill")
            risk_on_15 = (P15[self.REGIME_REF] > line15).fillna(False)
            scale_15 = risk_on_15.astype(float)
        else:
            scale_15 = scale_d.reindex(P15.index, method="ffill").fillna(0.0)
            risk_on_15 = scale_15 > 0.0
        mom = P15 / ref90_15 - 1
        rank = mom.rank(axis=1, ascending=False, method="first")

        # --- hard gates: per-coin trend (asymmetric entry option) & regime ---
        stay_trend = (known > known.rolling(self.PER_COIN_SMA).mean())
        if self.TREND_FILTER_ENABLE:
            stay_ok_15 = stay_trend.reindex(columns=P15.columns).reindex(P15.index, method="ffill").fillna(False)
            if self.COIN_FAST_SMA is not None:
                # asymmetric coin re-entry: SMA(COIN_FAST_SMA) entry while the
                # standard regime is CONFIRMED, SMA(PER_COIN_SMA) otherwise
                fast_trend = (known > known.rolling(self.COIN_FAST_SMA).mean())
                fast_15 = fast_trend.reindex(columns=P15.columns).reindex(P15.index, method="ffill").fillna(False)
                confirmed_d = std.reindex(P15.index, method="ffill").fillna(False)
                enter_ok_15 = pd.DataFrame(
                    np.where(confirmed_d.to_numpy()[:, None],
                             fast_15.to_numpy(), stay_ok_15.to_numpy()),
                    index=P15.index, columns=P15.columns)
            else:
                enter_ok_15 = stay_ok_15
        else:
            stay_ok_15 = pd.DataFrame(True, index=P15.index, columns=P15.columns)
            enter_ok_15 = stay_ok_15
        gate_enter = enter_ok_15.apply(lambda col: col & risk_on_15)
        gate_stay = stay_ok_15.apply(lambda col: col & risk_on_15)

        exit_n = self.TOP_N if self.EXIT_RANK_N is None else self.EXIT_RANK_N
        enter_ok = (rank <= self.TOP_N) & gate_enter
        stay_ok = (rank <= exit_n) & gate_stay

        idx = P15.index[P15.index.minute == 0] if self.REBALANCE_HOURLY else P15.index
        held = self._hysteresis_membership(rank.loc[idx], enter_ok.loc[idx], stay_ok.loc[idx])
        want = held.reindex(P15.index, method="ffill").fillna(False).astype(bool)
        self._xs = want
        self._scale_15 = scale_15
        self._xs_key = key
        return self._xs

    # ----------------------------------------------------------------
    # scale column attached alongside the frozen hold flag
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)   # sets 'hold'
        want = self._compute_xs()
        s = self._scale_15
        if s is None or len(s) == 0:
            dataframe["bull_scale"] = 1.0
            return dataframe
        left = pd.DataFrame({"date": pd.to_datetime(dataframe["date"], utc=True)})
        m = pd.merge_asof(left.sort_values("date"),
                          s.rename("sc").reset_index().rename(columns={"index": "date"}).sort_values("date"),
                          on="date", direction="backward")
        dataframe["bull_scale"] = m["sc"].fillna(0.0).to_numpy()
        return dataframe

    def _bull_scale(self, df) -> float:
        if df is None or len(df) == 0:
            return 0.0
        v = df.iloc[-1].get("bull_scale")
        try:
            return float(v)
        except (TypeError, ValueError):
            return 1.0

    # --- liquidity-aware sizing: frozen parent logic, target scaled by the
    #     regime scale (identical to frozen when scale == 1.0) ---
    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        if self.dp.runmode.value in ("plot", "other"):
            return proposed_stake
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        scale = self._bull_scale(df)
        target = self._portfolio_value() * scale / self.TOP_N
        stake = min(proposed_stake, target, fillable, max_stake)
        if min_stake and stake < min_stake:
            return 0.0
        return max(stake, 0.0)

    # --- verbatim copy of frozen OPT2 adjust_trade_position with exactly two
    #     deltas: (1) accumulation target scaled by bull_scale; (2) when the
    #     regime downgrades to a HALF state (scale<1) positions above target
    #     are trimmed down to it (liquidity-capped) — at scale==1.0 every
    #     branch is frozen-identical. ---
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
        fr = last.get("funding_rate")
        if self.FUNDING_GATE_MODE == "q80":
            thr = last.get("funding_gate_thr")
            if pd.notna(fr) and pd.notna(thr) and float(fr) > float(thr):
                return None
        else:
            if pd.notna(fr) and float(fr) > self.funding_max:
                return None
        scale = self._bull_scale(df)
        target = pv * scale / self.TOP_N
        if scale < 1.0 and current_value > target * 1.02:
            # regime downgraded to a half state: de-risk down to the scaled target
            sellable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
            reduce = -min(current_value - target, sellable)
            if reduce >= 0:
                return None
            if min_stake and abs(reduce) < min_stake:
                return None
            return reduce
        if current_value >= target * 0.98:
            return None   # already at target weight
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        add = min(target - current_value, fillable, max_stake)
        if add <= 0 or (min_stake and add < min_stake):
            return None
        return add
