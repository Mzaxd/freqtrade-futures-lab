# CHOP_MeanRev — research_chop WS-C1: gated mean-reversion sleeve C (2026-11-04).
#
# Independent third sleeve. NO inheritance from the OPT4 family (and no import
# of any oss strategy): the only shared DNA is the lab-standard sizing idiom
# (1% equity risk, OPT7_NFILite's stoploss_from_absolute pattern).
#
# Pre-registered design (PRE_REGISTRATION.md §2/§2.1 + WS-C1 task):
#   GATES (computed in populate_indicators on the strategy's OWN dataframe —
#   in backtest mode that parameter is the FULL loaded history, so a 720 h
#   rolling rank is safe; get_analyzed_dataframe is FORBIDDEN here because of
#   its 1000-candle truncation). Formulas verbatim from PRE_REG §2:
#     ret_1h = log(close).diff();  vol_12h = ret_1h.rolling(12).std()
#     mom_72h = log(close).diff(72);  mom_z = mom_72h / (vol_12h*sqrt(72))
#     TR = max(h-l, |h-pc|, |l-pc|);  atr_pct = TR.rolling(14).mean()/close
#     atr_pct_rank = atr_pct.rolling(720, min_periods=240).rank(pct=True)
#     g2 = |mom_z| < 1.25 AND atr_pct_rank >= 0.90          (violent chop)
#     g4 = trailing 240 h fraction of (|mom_z| < 1.25) >= 0.90 (persistent chop)
#   Class parameter gate in {"g2","g4"} selects which gate masks entries.
#
#   ENTRY: Bollinger(bb_period in {96,168}, bb_ndev in {2.0,2.5}, SMA) on 1h.
#     close < lower band AND gate ON -> long next candle open;
#     close > upper band AND gate ON -> short next candle open. can_short.
#   EXIT (three layers):
#     1. mean reversion target: close back at/through the middle band
#        (populate_exit_trend, candle close);
#     2. time stop: 48 h hold -> custom_exit "mr_time_48h";
#     3. initial ATR stop 1.5 x ATR(14) anchored at the entry signal candle
#        (custom_stoploss + stoploss_from_absolute; fixed absolute price, no
#        trailing). ATR implemented as SMA(14) of TR — same core as the
#        pre-registered atr_pct feature (NOT Wilder-smoothed talib ATR).
#        Catastrophe backstop stoploss = -0.15.
#   SIZING: 1% equity risk per trade: stop_pct = max(1.5*ATR/signal_close,
#     0.005 floor); notional = equity*0.01/stop_pct; stake = notional/lev(=2)
#     capped at 35% of equity as margin. position_adjustment_enable=False.
#     max_open_trades left at config default (4).
#
# Grid identity: 8 pre-registered subclasses at file bottom
#   gate{g2,g4} x bb_period{96,168} x bb_ndev{2.0,2.5}. Nothing else varies.
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from pandas import DataFrame
from talib import abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class CHOP_MeanRev(IStrategy):
    """Gated Bollinger band-fade, bidirectional, small size (WS-C1)."""

    INTERFACE_VERSION = 3

    timeframe = "1h"
    # mom_z needs 72 h, atr_pct_rank needs a full 720 h window (min 240):
    # 900 guarantees every decision row sees a complete trailing window.
    startup_candle_count = 900

    can_short = True
    position_adjustment_enable = False
    max_entry_position_adjustment = 0
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    use_custom_stoploss = True
    stoploss = -0.15          # catastrophe backstop only
    minimal_roi = {"0": 100}  # ROI exits off

    # --- pre-registered parameter space (WS-C1; DO NOT widen) ---------------
    gate = "g2"          # {"g2", "g4"}
    bb_period = 96       # {96, 168}
    bb_ndev = 2.0        # {2.0, 2.5}
    stop_atr_mult = 1.5  # initial stop width in ATR(14)
    stop_pct_floor = 0.005
    max_hold_h = 48.0    # time stop
    risk_pct = 0.01      # equity risked per trade
    margin_cap = 0.35    # max stake (margin) as fraction of equity
    lev = 2.0

    # cache: pair -> (n_rows, atr_series, close_series); rebuilt only when the
    # causal frame grows (OPT9_Recycle idiom)
    _causal_cache: dict = {}

    # ------------------------------------------------------------------ setup
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag,
                 side: str, **kwargs) -> float:
        return self.lev

    # ------------------------------------------------------------- indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe
        # --- gate features, verbatim PRE_REG §2 (all trailing windows) ------
        logc = np.log(df["close"])
        ret_1h = logc.diff()
        vol_12h = ret_1h.rolling(12).std()
        df["mom_z"] = logc.diff(72) / (vol_12h * np.sqrt(72))
        pc = df["close"].shift(1)
        tr = pd.concat(
            [df["high"] - df["low"],
             (df["high"] - pc).abs(),
             (df["low"] - pc).abs()], axis=1).max(axis=1)
        atr_pct = tr.rolling(14).mean() / df["close"]
        df["atr_pct_rank"] = atr_pct.rolling(720, min_periods=240).rank(pct=True)

        g1 = (df["mom_z"].abs() < 1.25).fillna(False)
        g2 = (g1 & (df["atr_pct_rank"] >= 0.90)).fillna(False)
        g1s = pd.Series(np.where(df["mom_z"].isna(), np.nan, g1.astype(float)),
                        index=df.index)
        g4 = (g1s.rolling(240, min_periods=240).mean() >= 0.90).fillna(False)
        df["g2_on"] = g2
        df["g4_on"] = g4
        df["gate_on"] = g2 if self.gate == "g2" else g4

        # --- Bollinger bands (SMA, symmetric ndev) --------------------------
        bb = ta.BBANDS(df, timeperiod=self.bb_period, nbdevup=self.bb_ndev,
                       nbdevdn=self.bb_ndev, matype=0)
        df["bb_u"] = bb["upperband"]
        df["bb_m"] = bb["middleband"]
        df["bb_l"] = bb["lowerband"]

        # --- ATR(14) column (SMA of TR; same core as atr_pct above) ---------
        df["mr_atr"] = tr.rolling(14).mean()
        return df

    # ----------------------------------------------------------------- entry
    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[:, "enter_long"] = 0
        df.loc[:, "enter_short"] = 0
        on = df["gate_on"].astype(bool)
        df.loc[(df["close"] < df["bb_l"]) & on, "enter_long"] = 1
        df.loc[(df["close"] > df["bb_u"]) & on, "enter_short"] = 1
        return df

    # ------------------------------------------------------------------ exit
    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[:, "exit_long"] = 0
        df.loc[:, "exit_short"] = 0
        # target: reversion back to the middle band
        df.loc[df["close"] >= df["bb_m"], "exit_long"] = 1
        df.loc[df["close"] <= df["bb_m"], "exit_short"] = 1
        return df

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # time stop (freqtrade-supported interface; evaluated every candle)
        age_h = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if age_h >= self.max_hold_h:
            return "mr_time_48h"
        return None

    # causal accessor: raw frame from dp.get_pair_dataframe (full history in
    # backtest, cut at current candle by freqtrade) + our own strict slice at
    # ts; returns (atr, close) of the SIGNAL candle (last closed before ts).
    def _signal_atr_close(self, pair: str, ts: datetime):
        df = self.dp.get_pair_dataframe(pair, self.timeframe)
        if df is None or len(df) == 0:
            return None, None
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        idx = int(df["date"].searchsorted(t.floor("ms"))) - 1
        if idx < 20:
            return None, None
        cached = self._causal_cache.get(pair)
        if cached is None or cached[0] != len(df):
            pc = df["close"].shift(1)
            tr = pd.concat(
                [df["high"] - df["low"],
                 (df["high"] - pc).abs(),
                 (df["low"] - pc).abs()], axis=1).max(axis=1)
            self._causal_cache[pair] = (len(df), tr.rolling(14).mean(), df["close"])
        _, atr_s, close_s = self._causal_cache[pair]
        return float(atr_s.iloc[idx]), float(close_s.iloc[idx])

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs):
        # initial ATR stop anchored at the entry signal candle; fixed absolute
        # price, no trailing (stoploss_from_absolute per candle).
        atr, _ = self._signal_atr_close(pair, trade.open_date_utc)
        if not atr or atr <= 0 or np.isnan(atr):
            return None
        lev = float(trade.leverage) if trade.leverage else self.lev
        if trade.is_short:
            stop_price = trade.open_rate + self.stop_atr_mult * atr
            return stoploss_from_absolute(stop_price, current_rate,
                                          is_short=True, leverage=lev)
        stop_price = trade.open_rate - self.stop_atr_mult * atr
        return stoploss_from_absolute(stop_price, current_rate,
                                      is_short=False, leverage=lev)

    # --------------------------------------------------------------- sizing
    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake, max_stake: float, leverage: float,
                            entry_tag, side: str, **kwargs) -> float:
        try:
            atr, close = self._signal_atr_close(pair, current_time)
            if not atr or atr <= 0 or np.isnan(atr) or not close or close <= 0:
                return proposed_stake
            stop_pct = max(self.stop_atr_mult * atr / close, self.stop_pct_floor)
            equity = self.wallets.get_total_stake_amount()
            notional = equity * self.risk_pct / stop_pct
            stake = notional / self.lev            # leverage 2 -> margin half
            stake = min(stake, equity * self.margin_cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
            return stake
        except Exception:
            return proposed_stake


# --- 8 pre-registered grid points (IS selection only; OS runs the winner) ---
class CHOP_MR_g2_96_20(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g2", 96, 2.0


class CHOP_MR_g2_96_25(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g2", 96, 2.5


class CHOP_MR_g2_168_20(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g2", 168, 2.0


class CHOP_MR_g2_168_25(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g2", 168, 2.5


class CHOP_MR_g4_96_20(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g4", 96, 2.0


class CHOP_MR_g4_96_25(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g4", 96, 2.5


class CHOP_MR_g4_168_20(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g4", 168, 2.0


class CHOP_MR_g4_168_25(CHOP_MeanRev):
    gate, bb_period, bb_ndev = "g4", 168, 2.5
