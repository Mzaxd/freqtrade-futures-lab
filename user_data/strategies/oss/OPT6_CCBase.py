# OPT6_CCBase — phase-6 stop-loss CLUSTER-CONTROL family + ER hybrid (Agent-L).
#
# Hypothesis under test (phase-5 forensics): weak-window drawdowns (22H2 12.03%,
# 23H1 14.90%) come from correlated stop clusters — concurrent positions opened
# in the same regime share similar ATR stop distances and are stopped together
# when the move reverses. Entry-side filters were proven structurally useless;
# these variants attack INTER-POSITION correlation instead.
#
# All variants inherit the FROZEN OPT4_VolatilitySystem (atr08 entry gate, 60d
# time stop, 1%-equity risk sizing, ATR-anchored initial stop, factory signals
# 2.0 / 3h / 2.0, long/short symmetric, no DCA, MOT via config). Variants only:
#   CC1a/CC1b — global rolling-24h NEW-entry cap K=2/K=3 (fill basis, open and
#               closed trades both counted) via confirm_trade_entry rejection.
#   CC2       — per-side concurrent cap (max 2 longs + 2 shorts).
#   CC3       — stop staggering: the n-th concurrent position uses
#               stop_atr_mult = 2.0 + 0.5*(n-1), capped at 3.5. Wider stop +
#               the 1%-risk model auto-shrinks size => de-correlated cluster.
#               Tier is determined CAUSALLY at entry (from trades open at that
#               moment) and frozen in a (pair, open_ts) cache so that
#               custom_stake_amount and custom_stoploss use the SAME tier —
#               the 1%-risk semantics hold trade-by-trade.
#   HYB_*     — each CC variant x the phase-5 ER1h-025 entry gate
#               (1h Kaufman ER(28) >= 0.25, entries only; reimplemented here
#               after OPT5_GateBase/OPT5_Gate_ER1h025 — their files untouched).
#
# Exits are NEVER touched by any variant (exit trend / time stop / reverse
# signal inherited unchanged from OPT4).
from datetime import datetime, timedelta

from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute

from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT6_CCBase(OPT4_VolatilitySystem):
    # ---- cluster-control knobs (None / False = mechanism off) ----
    cc1_max_entries_24h = None    # CC1a/CC1b: global rolling-24h new-entry cap K
    cc2_max_same_side = None      # CC2: per-side concurrent cap
    cc3_stagger = False           # CC3: stop-distance staggering on
    cc3_base_mult = 2.0           # tier-1 multiplier (== frozen OPT4 stop)
    cc3_step = 0.5
    cc3_cap = 3.5

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # (pair, open_ts) -> frozen stop multiplier; written at sizing time,
        # read by custom_stoploss. Fresh per strategy instance.
        self._cc3_mult_cache: dict = {}

    # ------------------------------------------------------------------ helpers
    def _opened_in_window(self, now: datetime, hours: int = 24) -> int:
        """Number of trades (open OR closed — fill basis) whose open_date falls
        within the last `hours` before `now`. Global across all pairs."""
        since = now - timedelta(hours=hours)
        n = sum(1 for t in Trade.get_trades_proxy(is_open=True)
                if t.open_date_utc >= since)
        n += sum(1 for t in Trade.get_trades_proxy(is_open=False)
                 if t.open_date_utc >= since)
        return n

    def _open_by_side(self, side: str) -> int:
        want_short = (side == "short")
        return sum(1 for t in Trade.get_trades_proxy(is_open=True)
                   if t.is_short == want_short)

    # ------------------------------------------------------- entry admission
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        if (self.cc1_max_entries_24h is not None
                and self._opened_in_window(current_time) >= self.cc1_max_entries_24h):
            return False
        if (self.cc2_max_same_side is not None
                and self._open_by_side(side) >= self.cc2_max_same_side):
            return False
        return True

    # ------------------------------------------------------------- CC3 tiering
    def _cc3_mult(self, n_concurrent_prior: int) -> float:
        """Tier multiplier for the (n_concurrent_prior+1)-th concurrent position."""
        return min(self.cc3_base_mult + self.cc3_step * n_concurrent_prior,
                   self.cc3_cap)

    def _cc3_mult_now(self, current_time: datetime) -> float:
        """Tier from trades open at current_time (all opened <= now): causal."""
        return self._cc3_mult(len(Trade.get_trades_proxy(is_open=True)))

    def _cc3_mult_for_trade(self, trade: Trade) -> float:
        key = (trade.pair, trade.open_date_utc)
        if key in self._cc3_mult_cache:
            return self._cc3_mult_cache[key]
        # Fallback (cache miss should not happen): causal recount of trades that
        # were already open at this trade's open moment.
        t0 = trade.open_date_utc
        prior = 0
        for p in Trade.get_trades_proxy(is_open=True):
            if p.id != trade.id and p.open_date_utc <= t0:
                prior += 1
        for p in Trade.get_trades_proxy(is_open=False):
            if p.open_date_utc <= t0 and (p.close_date_utc or t0) > t0:
                prior += 1
        return self._cc3_mult(prior)

    # ------------------------------------------------------------------ sizing
    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        if not self.cc3_stagger:
            return super().custom_stake_amount(
                pair, current_time, current_rate, proposed_stake, min_stake,
                max_stake, leverage, entry_tag, side, **kwargs)
        # identical risk sizing to OPT1/OPT4 except stop_pct uses the staggered
        # tier multiplier (same tier the stop will use => risk stays 1%).
        try:
            df, idx = self._signal_candle(pair, current_time)
            row = df.iloc[idx]
            atr = float(row["atr_raw"])
            close = float(row["close"])
            if not atr or atr <= 0 or not close or close <= 0:
                return proposed_stake
            mult = self._cc3_mult_now(current_time)
            self._cc3_mult_cache[(pair, current_time)] = mult
            stop_pct = max(mult * atr / close, self.stop_pct_floor)
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = notional / max(leverage, 1.0)
            stake = min(stake, equity * self.margin_cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    # ------------------------------------------------------------------- stop
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> float | None:
        if not self.cc3_stagger:
            return super().custom_stoploss(
                pair, trade, current_time, current_rate, current_profit,
                after_fill, **kwargs)
        # ATR-anchored initial stop (no trailing) at the staggered distance.
        try:
            df, idx = self._signal_candle(pair, trade.open_date_utc)
            atr_entry = float(df.iloc[idx]["atr_raw"])
        except Exception:
            return None
        if not atr_entry or atr_entry <= 0:
            return None
        mult = self._cc3_mult_for_trade(trade)
        lev = trade.leverage or 1.0
        if trade.is_short:
            stop_price = trade.open_rate + mult * atr_entry
            return stoploss_from_absolute(stop_price, current_rate,
                                          is_short=True, leverage=lev)
        stop_price = trade.open_rate - mult * atr_entry
        return stoploss_from_absolute(stop_price, current_rate,
                                      is_short=False, leverage=lev)


# ----------------------------------------------------------------- variants
class OPT6_CC1a(OPT6_CCBase):
    """Rolling-24h new-entry cap K=2 (global)."""
    cc1_max_entries_24h = 2


class OPT6_CC1b(OPT6_CCBase):
    """Rolling-24h new-entry cap K=3 (global)."""
    cc1_max_entries_24h = 3


class OPT6_CC2(OPT6_CCBase):
    """Per-side concurrent cap: max 2 longs AND max 2 shorts."""
    cc2_max_same_side = 2


class OPT6_CC3(OPT6_CCBase):
    """Stop staggering: 2.0 / 2.5 / 3.0 / 3.5 by concurrent tier."""
    cc3_stagger = True


# --------------------------------------------------- ER1h-025 gate mixin (HYB)
class _OPT6_ERGateMixin:
    """1h Kaufman efficiency-ratio entry gate, ER(28) >= 0.25 — entries only.
    Reimplemented from the phase-5 OPT5_Gate_ER1h025 spec (files untouched):
    ER = |close.diff(28)| / close.diff().abs().rolling(28).sum(), computed on
    the just-closed 1h row, acted on at the next row's open. NaN blocks."""
    er_min = 0.25

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        er_n = 28
        net_move = (dataframe["close"] - dataframe["close"].shift(er_n)).abs()
        path_len = (dataframe["close"].diff().abs()
                    .rolling(er_n, min_periods=er_n).sum())
        dataframe["g2_er1h"] = net_move / path_len
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # full inherited stack first (raw signals + atr08 gate + CC caps apply
        # separately in confirm_trade_entry); the ER gate only removes entries.
        dataframe = super().populate_entry_trend(dataframe, metadata)
        ok = (dataframe["g2_er1h"] >= self.er_min).fillna(False)
        dataframe.loc[~ok, ["enter_long", "enter_short"]] = 0
        return dataframe


class OPT6_HYB_CC1a_ER1h(_OPT6_ERGateMixin, OPT6_CC1a):
    pass


class OPT6_HYB_CC1b_ER1h(_OPT6_ERGateMixin, OPT6_CC1b):
    pass


class OPT6_HYB_CC2_ER1h(_OPT6_ERGateMixin, OPT6_CC2):
    pass


class OPT6_HYB_CC3_ER1h(_OPT6_ERGateMixin, OPT6_CC3):
    pass
