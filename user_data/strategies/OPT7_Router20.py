# OPT7_Router20 — RegimeRouter 2.0: v1 skeleton + OPT4_VolatilitySystem legs.
#
# Phase-7 S5 salvage hypothesis: Router v1's legs were the lab's weaker sub
# engines; OPT4_VolatilitySystem (long/short volatility breakout, pool PF 2.0)
# replaces both trend legs. Skeleton retained verbatim from regime_router.py:
#   * causal regime series via regime_loader.attach_regime (rules pipeline,
#     exported for all 23 lab pairs by scripts/OPT7_regime_export.py; S5 runs
#     point FTLAB_REGIME_DIR at user_data/regimes_opt7, rows < 2024-01-01 only)
#   * slot routing + regime risk_scale, turbulent (3) and unknown (-1/NaN)
#     pause NEW entries; open trades keep their exits/stops
#   * meanrev leg = v1's frozen inline 4h Bollinger z-rejection engine
#   * per-tag budgets (risk / stop / time-stop), no DCA, no adding, ATR stop
#     on every trade, catastrophe backstop -0.30
#
# volsys leg = OPT4_VolatilitySystem imported UNCHANGED (frozen 2.0/2.0/0.8
# gate/60d time stop/1% risk/2x leverage); this file only routes its entries
# and scales its risk budget. Its exits derive from the RAW signal (never
# gated), exactly as in OPT4.
#
# Three pre-declared variants (routing policy is the ONLY difference):
#   OPT7_Router20A — adverse-veto + grade scale (v1 iter-11 pattern mapped to
#       a two-sided leg: long entries allowed in {trend_up, range}, short in
#       {trend_dn, range}; risk 1.0x aligned / 0.5x range; adverse-exit when
#       the opposite trend state confirms).
#   OPT7_Router20B — strict slots: long only in trend_up, short only in
#       trend_dn, full risk; same exits as A. (Tests whether iter-11's
#       "permission-gating cuts the best trades" lesson transfers to
#       breakout legs.)
#   OPT7_Router20C — static control: both sides allowed in every non-turbulent
#       state at constant risk, NO regime exits. (Isolates the value of the
#       regime series beyond the turbulent pause.)
from datetime import datetime, timedelta

from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

from regime_router import RegimeRouter
from regime_loader import risk_scale_for_regime
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT7_Router20Base(RegimeRouter, OPT4_VolatilitySystem):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 1000  # covers 4h EMA200 informative + 30d gate median

    order_types = {"entry": "market", "exit": "market", "stoploss": "market",
                   "stoploss_on_exchange": False}
    minimal_roi = {"0": 100.0}
    stoploss = -0.30
    use_custom_stoploss = True
    use_exit_signal = True   # required so custom_exit is invoked (v1 quirk)
    position_adjustment_enable = False

    # volsys-leg budget = OPT4 frozen constants (re-declared for transparency;
    # values are identical to the imported class)
    VS_RISK = 0.01
    VS_LEV = 2.0
    VS_MARGIN_CAP = 0.35
    VS_TIME_D = 60
    # meanrev-leg budget = v1 frozen constants (inherited MR_* from RegimeRouter)
    MR_LEV = 3
    MR_MARGIN_CAP = 0.25

    # ---------------- routing policy hooks (variant override points) ----------------
    def _vol_entry_ok(self, reg, is_short: bool):
        """reg: the regime Series; returns boolean entry mask (NaN-safe)."""
        raise NotImplementedError

    def _vol_scale(self, regime: float, is_short: bool) -> float:
        raise NotImplementedError

    def _vol_adverse_exit(self) -> bool:
        raise NotImplementedError

    # ---------------- indicators ----------------
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # regime onto the 1h frame (v1 path) ...
        dataframe = RegimeRouter.populate_indicators(self, dataframe, metadata)
        # ... then OPT4's resampled ATR/close_change/gate columns (unchanged)
        dataframe = OPT4_VolatilitySystem.populate_indicators(self, dataframe, metadata)
        return dataframe

    # ---------------- entries ----------------
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # OPT4 raw signals + atr08 gate (verbatim; gate on NEW entries only)
        thr = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        long_sig = dataframe["close_change"] > thr
        short_sig = dataframe["close_change"] * -1 > thr
        gate = (dataframe["atr_raw"] >= self.gate_atr_mult * dataframe["gate_atr_med"]).fillna(False)
        lg_raw = (long_sig & gate).fillna(False)
        sh_raw = (short_sig & gate).fillna(False)

        reg = dataframe["regime"]
        lg = lg_raw & self._vol_entry_ok(reg, False)
        sh = sh_raw & self._vol_entry_ok(reg, True)

        # meanrev leg (v1): range-only 4h z-rejection, yields to volsys signals
        rg = reg == 2
        mr_l = (dataframe["mr_long_4h"] == 1) & rg & (~lg_raw)
        mr_s = (dataframe["mr_short_4h"] == 1) & rg & (~sh_raw)

        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe.loc[lg, "enter_long"] = 1
        dataframe.loc[mr_l, "enter_long"] = 1
        dataframe.loc[sh, "enter_short"] = 1
        dataframe.loc[mr_s, "enter_short"] = 1
        dataframe.loc[mr_l | mr_s, "enter_tag"] = "meanrev"
        dataframe.loc[(lg & ~mr_l) | (sh & ~mr_s), "enter_tag"] = "volsys"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe  # per-tag exits in custom_exit (v1 pattern)

    # ---------------- budgets ----------------
    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(self.VS_LEV if (entry_tag or "volsys") == "volsys" else self.MR_LEV,
                   max_leverage)

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        tag = entry_tag or "volsys"
        try:
            df, idx = self._last_closed(pair, current_time)
            row = df.iloc[idx]
            regime = float(row["regime"]) if row["regime"] == row["regime"] else -1.0
            if tag == "volsys":
                atr = float(row.get("atr_raw") or 0)
                close = float(row["close"])
                if atr <= 0 or close <= 0:
                    return proposed_stake
                stop_pct = max(float(self.stop_atr_mult.value) * atr / close,
                               self.stop_pct_floor)
                risk = self.VS_RISK * self._vol_scale(regime, side == "short")
                if risk <= 0:
                    return 0.0
                equity = self.wallets.get_total_stake_amount()
                stake = equity * risk / stop_pct / max(leverage, 1.0)
                stake = min(stake, equity * self.VS_MARGIN_CAP, max_stake)
            else:  # meanrev: v1 sizing path verbatim (conf-scaled in range)
                atr = float(row.get("atr4_4h") or 0)
                if atr <= 0:
                    return proposed_stake
                stop_pct = max(self.MR_ATR_STOP * atr / float(row["close"]), 0.004)
                risk = risk_scale_for_regime(int(regime), float(row.get("conf", 0) or 0),
                                             self.MR_RISK)
                if risk <= 0:
                    return 0.0
                equity = self.wallets.get_total_stake_amount()
                stake = equity * risk / stop_pct / max(leverage, 1.0)
                stake = min(stake, equity * self.MR_MARGIN_CAP, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair, trade: Trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        tag = trade.enter_tag or "volsys"
        try:
            df, idx = self._last_closed(pair, trade.open_date_utc)
            row = df.iloc[idx]
            atr = float(row["atr_raw"] if tag == "volsys" else row.get("atr4_4h") or 0)
        except Exception:
            return None
        if atr <= 0:
            return None
        mult = float(self.stop_atr_mult.value) if tag == "volsys" else self.MR_ATR_STOP
        lev = trade.leverage or 1.0
        if trade.is_short:
            stop_price = trade.open_rate + mult * atr
            return stoploss_from_absolute(stop_price, current_rate,
                                          is_short=True, leverage=lev)
        stop_price = trade.open_rate - mult * atr
        return stoploss_from_absolute(stop_price, current_rate,
                                      is_short=False, leverage=lev)

    def custom_exit(self, pair, trade: Trade, current_time, current_rate,
                    current_profit, **kwargs):
        tag = trade.enter_tag or "volsys"
        try:
            df, idx = self._last_closed(pair, current_time)
            row = df.iloc[idx]
            regime = self._iv(row.get("regime")) if row.get("regime") == row.get("regime") else -1
            if tag == "volsys":
                if (current_time - trade.open_date_utc).days >= self.VS_TIME_D:
                    return "time_stop_60d"
                if self._vol_adverse_exit():
                    if (not trade.is_short and regime == 1) or (trade.is_short and regime == 0):
                        return "adverse_regime_exit"
                # reverse RAW signal closes the position (OPT4 exit, never
                # gated): threshold = PREVIOUS candle's ATR x signal mult
                prev = df.iloc[idx - 1] if idx > 0 else row
                thr = float(prev.get("atr_raw") or 0) * float(self.signal_atr_mult.value)
                cc = float(row.get("close_change") or 0) if row.get("close_change") == row.get("close_change") else 0.0
                if not trade.is_short and (-cc > thr):
                    return "vs_reverse_signal"
                if trade.is_short and (cc > thr):
                    return "vs_reverse_signal"
                return None
            # meanrev: v1 exit logic verbatim
            if current_time - trade.open_date_utc > timedelta(hours=self.MR_TIME_H):
                return "time_stop"
            if regime in (0, 1):
                return "adverse_regime_exit"
            col = "mr_exit_long_4h" if not trade.is_short else "mr_exit_short_4h"
            if self._iv(row.get(col)) == 1:
                return "mr_signal_exit"
        except Exception:
            return None
        return None


class OPT7_Router20A(OPT7_Router20Base):
    """Adverse-veto + grade scale (v1 iter-11 pattern mapped to OPT4's legs)."""
    RANGE_RISK_MULT = 0.5  # inherited semantics: trend legs take half risk in range

    def _vol_entry_ok(self, reg, is_short):
        # long allowed in {trend_up, range}; short in {trend_dn, range};
        # opposite trend / turbulent / unknown(-1, NaN) vetoed
        return reg.isin([2, 1 if is_short else 0])

    def _vol_scale(self, regime, is_short):
        r = int(regime)
        aligned = 0 if not is_short else 1
        return 1.0 if r == aligned else self.RANGE_RISK_MULT

    def _vol_adverse_exit(self):
        return True


class OPT7_Router20B(OPT7_Router20Base):
    """Strict slot routing: long ONLY in trend_up, short ONLY in trend_dn."""

    def _vol_entry_ok(self, reg, is_short):
        return reg == (1 if is_short else 0)

    def _vol_scale(self, regime, is_short):
        return 1.0  # entries only occur inside the aligned slot

    def _vol_adverse_exit(self):
        return True


class OPT7_Router20C(OPT7_Router20Base):
    """Static control: no veto, no scaling, no regime exits; turbulent pause only."""

    def _vol_entry_ok(self, reg, is_short):
        return reg.isin([0, 1, 2])

    def _vol_scale(self, regime, is_short):
        return 1.0

    def _vol_adverse_exit(self):
        return False
