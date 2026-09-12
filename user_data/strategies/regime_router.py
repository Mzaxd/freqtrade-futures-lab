# Regime router: routes three independent sub-strategy logics by market state.
#
#   regime 0 trend_up  -> MomentumBreakout logic (4h Donchian breakout, long)
#   regime 1 trend_dn  -> TrendShort logic        (4h EMA cross, short, reduced size)
#   regime 2 range     -> MeanReversion logic     (1h Bollinger z + RSI2, both sides, small)
#   regime 3 turbulent -> no entries (pause); open trades keep their exits/stops
#
# Sub-signal sources: the 4h logics are computed on a 4h informative frame
# (@informative decorator merges only after the 4h candle closes); the 1h
# mean-reversion logic runs on the base frame. Each trade carries an enter_tag
# naming its sub-strategy; exits / stops / time-stops / risk budgets are all
# keyed by that tag. Risk scales with regime confidence; no martingale, no
# position adding; every trade has an ATR stop.
from datetime import datetime, timedelta

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    informative,
    stoploss_from_absolute,
)

from regime_loader import attach_regime, risk_scale_for_regime


class RegimeRouter(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 1000  # covers 200x4h EMA on the informative frame

    order_types = {"entry": "market", "exit": "market", "stoploss": "market",
                   "stoploss_on_exchange": False}
    minimal_roi = {"0": 100.0}
    stoploss = -0.30            # catastrophe backstop
    use_custom_stoploss = True
    use_exit_signal = True    # required: custom_exit is only invoked when this is True
    # (populate_exit_trend leaves exit columns unset; per-tag exits in custom_exit)
    position_adjustment_enable = False

    # ---------------- sub-strategy parameters (frozen a-priori values) ----------------
    # TrendLong (iter-5): EMA-cross engine; stop/trail = previous round's frozen
    # plateau values (3.0 / 4.2) - wide trailing was what made this engine work.
    TL_ATR_STOP = 3.0
    TL_ATR_TRAIL = 4.2
    TL_RISK = 0.010
    TL_TIME_H = 24 * 28

    TS_EMA_FAST, TS_EMA_SLOW, TS_EMA_TREND = 20, 50, 200
    TS_ADX_MIN = 18
    TS_ATR_STOP = 3.0
    TS_ATR_TRAIL = 4.2
    TS_RISK = 0.007
    TS_TIME_H = 24 * 21

    MR_BB_PERIOD = 30          # 5 days on 4h
    MR_BB_STD = 2.0
    MR_ATR_STOP = 2.0          # anchored initial stop (NO trail for MR)
    MR_ATR_TRAIL = None        # unused (MR exits: TP mid-band / stop / time)
    MR_RISK = 0.005
    MR_TIME_H = 24 * 7

    leverage_fixed = 3
    min_conf = 0.35
    RANGE_RISK_MULT = 0.5   # trend legs in range state take half risk (iter-13)
    # -----------------------------------------------------------------------------------

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # TrendLong / TrendShort (EMA-cross engines) + MeanReversion (4h bands)
        # on the 4h frame. MR was moved from 1h (iter-6): 1h MR was a cost
        # machine (222 trades, -1723 USDT in IS) and trailing stops are wrong
        # for mean reversion - here: entry at |z| extreme, TP at mid-band
        # cross, fixed anchored ATR stop, time stop (no trailing).
        dataframe["atr4"] = ta.ATR(dataframe, timeperiod=14)
        ef = ta.EMA(dataframe, timeperiod=self.TS_EMA_FAST)
        es = ta.EMA(dataframe, timeperiod=self.TS_EMA_SLOW)
        et = ta.EMA(dataframe, timeperiod=self.TS_EMA_TREND)
        adx = ta.ADX(dataframe, timeperiod=14)
        # State-level trend conditions (iter-7): entries are LEVELS, not cross
        # events - a cross event usually fires before the regime confirms, so
        # event-and-state almost never coincide. Position lifecycle is state
        # driven: enter while state holds, exit when the state leaves.
        dataframe["tl_enter"] = (
            (ef > es) & (dataframe["close"] > et) & (adx > self.TS_ADX_MIN)
        ).astype(int)
        dataframe["ts_enter"] = (
            (ef < es) & (dataframe["close"] < et) & (adx > self.TS_ADX_MIN)
        ).astype(int)
        dataframe["tl_exit"] = ((ef < es)).astype(int)
        dataframe["ts_exit"] = ((ef > es)).astype(int)

        mid = ta.SMA(dataframe, timeperiod=self.MR_BB_PERIOD)
        std = dataframe["close"].rolling(self.MR_BB_PERIOD).std()
        z = (dataframe["close"] - mid) / std
        # iter-8: enter on REJECTION (z crosses back inside the band), not while
        # price sits at the extreme - "range" (|mom_z|<1.25) still contains mild
        # drift, and fading an ongoing drift loses (IS WR was 3-8%).
        dataframe["mr_long"] = ((z.shift(1) <= -self.MR_BB_STD) & (z > -self.MR_BB_STD)).astype(int)
        dataframe["mr_short"] = ((z.shift(1) >= self.MR_BB_STD) & (z < self.MR_BB_STD)).astype(int)
        dataframe["mr_exit_long"] = (
            (dataframe["close"] > mid) & (dataframe["close"].shift(1) <= mid.shift(1))
        ).astype(int)
        dataframe["mr_exit_short"] = (
            (dataframe["close"] < mid) & (dataframe["close"].shift(1) >= mid.shift(1))
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # base 1h frame: only regime attachment (all sub-logics live on 4h)
        dataframe = attach_regime(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # iter-11: adverse-VETO routing. The detector's trend_up (72h momentum
        # bursts, ~14% of time) is narrower than what makes the EMA engine money
        # (sustained drift, often labelled "range"): permission-gating cut the
        # best trades. Trend legs now trade in ANY non-adverse state and are
        # only vetoed in the opposite trend / turbulent; MR stays range-only.
        tl_ok = ~dataframe["regime"].isin([1, 3])
        ts_ok = ~dataframe["regime"].isin([0, 3])
        rg = dataframe["regime"] == 2

        tl = (dataframe["tl_enter_4h"] == 1) & tl_ok
        ts = (dataframe["ts_enter_4h"] == 1) & ts_ok
        mr_l = (dataframe["mr_long_4h"] == 1) & rg & (tl != 1)
        mr_s = (dataframe["mr_short_4h"] == 1) & rg & (ts != 1)

        dataframe.loc[tl | mr_l, "enter_long"] = 1
        dataframe.loc[tl, "enter_tag"] = "trendlong"
        dataframe.loc[mr_l, "enter_tag"] = "meanrev"
        dataframe.loc[ts | mr_s, "enter_short"] = 1
        dataframe.loc[ts, "enter_tag"] = "trendshort"
        dataframe.loc[mr_s, "enter_tag"] = "meanrev"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe  # per-tag exits in custom_exit

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _iv(x) -> int:
        """NaN-safe int(x): NaN/None -> 0 (NaN is truthy, int(NaN) raises)."""
        try:
            return int(x)
        except (TypeError, ValueError):
            return 0

    def _last_closed(self, pair: str, until: datetime):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        return df, df["date"].searchsorted(until) - 1

    def _budget(self, tag: str) -> tuple[float, float, float, int]:
        """(risk, atr_stop_mult, atr_trail_mult, time_stop_hours) per sub-strategy."""
        if tag == "trendlong":
            return self.TL_RISK, self.TL_ATR_STOP, self.TL_ATR_TRAIL, self.TL_TIME_H
        if tag == "trendshort":
            return self.TS_RISK, self.TS_ATR_STOP, self.TS_ATR_TRAIL, self.TS_TIME_H
        return self.MR_RISK, self.MR_ATR_STOP, self.MR_ATR_TRAIL, self.MR_TIME_H

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return min(self.leverage_fixed, max_leverage)

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            df, idx = self._last_closed(pair, current_time)
            row = df.iloc[idx]
            tag = entry_tag or "meanrev"
            risk, stop_mult, _, _ = self._budget(tag)
            atr = float(row.get("atr4_4h") or 0)  # all sub-logics are 4h-native now
            if atr <= 0:
                return proposed_stake
            stop_pct = max(stop_mult * atr / float(row["close"]), 0.004)
            # iter-11: trend legs sized by state grade (iter-12): full risk in
            # the aligned trend state, 0.6x in range (non-adverse but not
            # favorable) - recovers drawdown control lost to veto-routing.
            # MR keeps confidence-scaled sizing.
            regime = int(row.get("regime", -1)) if row.get("regime") == row.get("regime") else -1
            if tag == "meanrev":
                risk = risk_scale_for_regime(regime, float(row.get("conf", 0) or 0), risk)
            elif tag == "trendlong":
                risk *= 1.0 if regime == 0 else self.RANGE_RISK_MULT
            elif tag == "trendshort":
                risk *= 1.0 if regime == 1 else self.RANGE_RISK_MULT
            if risk <= 0:
                return 0.0
            equity = self.wallets.get_total_stake_amount()
            stake = equity * risk / stop_pct / max(leverage, 1.0)
            cap = 0.35 if tag != "meanrev" else 0.25
            stake = min(stake, equity * cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake

    def custom_stoploss(self, pair, trade: Trade, current_time, current_rate,
                        current_profit, after_fill, **kwargs):
        try:
            df, idx = self._last_closed(pair, trade.open_date_utc)
            row = df.iloc[idx]
            tag = trade.enter_tag or "meanrev"
            _, stop_mult, trail_mult, _ = self._budget(tag)
            atr = float(row.get("atr4_4h") or 0)
        except Exception:
            return None
        if atr <= 0:
            return None
        lev = trade.leverage or 1.0
        if trade.is_short:
            stop_price = trade.open_rate + stop_mult * atr
            if trail_mult:  # trend sub-strategies trail; MR uses the anchored stop only
                extreme = trade.min_rate or trade.open_rate
                stop_price = min(stop_price, extreme + trail_mult * atr)
            return stoploss_from_absolute(stop_price, current_rate,
                                          is_short=True, leverage=lev)
        stop_price = trade.open_rate - stop_mult * atr
        if trail_mult:
            extreme = trade.max_rate or trade.open_rate
            stop_price = max(stop_price, extreme - trail_mult * atr)
        return stoploss_from_absolute(stop_price, current_rate,
                                      is_short=False, leverage=lev)

    def custom_exit(self, pair, trade: Trade, current_time, current_rate,
                    current_profit, **kwargs):
        tag = trade.enter_tag or "meanrev"
        _, _, _, time_h = self._budget(tag)
        if current_time - trade.open_date_utc > timedelta(hours=time_h):
            return "time_stop"
        try:
            df, idx = self._last_closed(pair, current_time)
            row = df.iloc[idx]
            regime = self._iv(row.get("regime")) if row.get("regime") == row.get("regime") else -1
            # adverse-regime exit (iter-10): trend legs exit only when the state
            # turns ADVERSE (opposite trend); range episodes are ridden out with
            # the sub-strategy's own exits / trailing stop. MR premise breaks as
            # soon as any strong trend starts. turbulent never forces exits.
            adverse = {"trendlong": (1,), "trendshort": (0,), "meanrev": (0, 1)}
            if regime in adverse.get(tag, ()):
                return "adverse_regime_exit"
            if tag == "trendlong" and self._iv(row.get("tl_exit_4h")) == 1:
                return "tl_signal_exit"
            if tag == "trendshort" and self._iv(row.get("ts_exit_4h")) == 1:
                return "ts_signal_exit"
            if tag == "meanrev":
                col = "mr_exit_long_4h" if not trade.is_short else "mr_exit_short_4h"
                if self._iv(row.get(col)) == 1:
                    return "mr_signal_exit"
        except Exception:
            return None
        return None
