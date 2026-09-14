# FAI_V1.py — research_deepen/freqai: purged walk-forward triple-barrier classification
#
# PRE-REGISTERED design (research_deepen/freqai/report.md §0.2, frozen before any backtest):
#   * 11 causal, dimensionless features (multi-horizon log returns, realized vol,
#     momentum t-stat (regime_detector mom_z), ATR ratio, DK vol ratio, causal funding
#     (opt_common.attach_funding, read-only reuse), volume ratio).
#   * Triple-barrier binary label, string classes "up"/"dn": barriers at
#     close_t +/- 2*ATR14_t, 48h timeout; same-bar double-touch resolved by that bar's
#     close vs close_t; timeout resolved by close_{t+48} vs close_t.
#   * LightGBMClassifier via FreqAI, walk-forward train 30d / predict 7d,
#     purge via feature_parameters.buffer_train_data_candles = 48 (label horizon).
#   * Entries: P(up) >= 0.5+THR (long) / <= 0.5-THR (short), gated by do_predict==1.
#     THR from env FAI_THRESHOLD (default 0.02); thresholds only act AFTER prediction,
#     so all threshold arms share one model/prediction cache (identifier fai_v1).
#   * Exits mirror the barriers: SL at entry-signal-candle close -/+ 2*ATR14
#     (custom_stoploss pinned to a fixed price; fills at stop price), TP at the
#     opposite barrier via custom_exit (next-candle-open fill, disclosed conservative
#     bias), hard timeout at +48h from trade open (== 48 bars after signal close).
#     No signal-flip exit, no ROI ladder, no trailing stop.

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

# read-only reuse of the phase-1 helper (causal funding attach); do NOT modify it
_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "user_data" / "strategies" / "oss"))
import opt_common  # noqa: E402

logger = logging.getLogger(__name__)

FAI_THRESHOLD = float(os.environ.get("FAI_THRESHOLD", "0.02"))

# ---- frozen constants (pre-registered) ----------------------------------------
VOL_WINDOW = 12            # hours, fast realized vol
VOL_WINDOW_SLOW = 48       # hours, slow realized vol
MOM_WINDOW = 72            # hours, momentum horizon
RET_WINDOWS = (24, 72, 168)
RANK_WINDOW = 720          # hours, trailing median base for ratio features
FUNDING_MA = 72            # hours (~9 settlements) funding mean
LABEL_HORIZON = 48         # hours, triple-barrier timeout
LABEL_ATR_MULT = 2.0       # barriers at +/- 2 * ATR14


class FAI_V1(IStrategy):
    """
    Purged walk-forward LightGBM triple-barrier classifier (1h, futures, 12 pairs).
    Research strategy for research_deepen/freqai; class prefix FAI_ per charter.
    """

    timeframe = "1h"
    can_short = True
    process_only_new_candles = True

    startup_candle_count: int = 800  # > 720h rank window warmup (+ATR14)

    minimal_roi = {"0": 100}          # disabled; barriers handle exits
    stoploss = -0.99                  # mechanical backstop; real stop via custom_stoploss
    use_custom_stoploss = True
    use_exit_signal = True            # must be True: freqtrade gates custom_exit behind it

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    plot_config = {"main_plot": {}, "subplots": {"up-prob": {"up": {"color": "blue"}}}}

    # ------------------------------------------------------------------ features
    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        # no periodic features pre-registered; kept for interface completeness
        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        pair = metadata.get("pair", "")
        logc = np.log(dataframe["close"])
        ret1 = logc.diff()

        rvol_fast = ret1.rolling(VOL_WINDOW).std()
        rvol_slow = ret1.rolling(VOL_WINDOW_SLOW).std()

        for w in RET_WINDOWS:
            dataframe[f"%-ret_{w}h"] = logc.diff(w)
        dataframe["%-rvol_12h"] = rvol_fast
        dataframe["%-rvol_48h"] = rvol_slow
        # momentum t-stat (regime_detector mom_z): 72h move / (vol * sqrt(72))
        dataframe["%-mom_z_72h"] = logc.diff(MOM_WINDOW) / (
            rvol_fast * np.sqrt(MOM_WINDOW)
        )

        atr = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr14"] = atr                      # raw col (no % prefix): barrier ref
        atr_pct = atr / dataframe["close"]
        dataframe["%-atr_ratio"] = atr_pct / atr_pct.rolling(
            RANK_WINDOW, min_periods=RANK_WINDOW // 2
        ).median()
        dataframe["%-dk_vol_ratio"] = rvol_fast / rvol_fast.rolling(
            RANK_WINDOW, min_periods=RANK_WINDOW // 2
        ).median()

        # causal funding: rate of the settlement BEFORE the latest settled one
        dataframe = opt_common.attach_funding(dataframe, pair)
        fr = dataframe["funding_rate"].fillna(0.0)
        dataframe["%-funding_rate"] = fr
        dataframe["%-funding_ma3d"] = fr.rolling(FUNDING_MA, min_periods=24).mean()
        dataframe = dataframe.drop(columns=["funding_rate"])

        vol_ratio = dataframe["volume"] / dataframe["volume"].rolling(24).mean()
        dataframe["%-volume_rel_24h"] = vol_ratio.replace([np.inf, -np.inf], np.nan)

        # numeric hygiene: no inf anywhere in features
        feat_cols = [c for c in dataframe.columns if c.startswith("%-")]
        dataframe[feat_cols] = dataframe[feat_cols].replace([np.inf, -np.inf], np.nan)

        logger.info("FAI_V1 features for %s (thr=%.3f): %d cols", pair, FAI_THRESHOLD, len(feat_cols))
        return dataframe

    # -------------------------------------------------------------------- label
    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Triple-barrier binary label (string classes "up"/"dn"), forward-causal."""
        high = dataframe["high"].to_numpy(dtype=np.float64)
        low = dataframe["low"].to_numpy(dtype=np.float64)
        close = dataframe["close"].to_numpy(dtype=np.float64)
        atr = dataframe["atr14"].to_numpy(dtype=np.float64)

        n = len(close)
        up_bar = close + LABEL_ATR_MULT * atr
        dn_bar = close - LABEL_ATR_MULT * atr

        lab = np.full(n, np.nan, dtype=object)
        resolved = ~np.isfinite(up_bar) | ~np.isfinite(dn_bar)  # bad rows stay NaN

        for k in range(1, LABEL_HORIZON + 1):
            if k >= n:
                break
            h = np.full(n, np.nan); h[: n - k] = high[k:]
            l = np.full(n, np.nan); l[: n - k] = low[k:]
            c = np.full(n, np.nan); c[: n - k] = close[k:]

            up = (h >= up_bar) & ~resolved
            dn = (l <= dn_bar) & ~resolved
            tie = up & dn
            tie_up = tie & (c > close)
            lab[(up & ~tie) | tie_up] = "up"
            lab[(dn & ~tie) | (tie & ~tie_up)] = "dn"
            resolved |= up | dn

        # timeout: resolve by close_{t+48} vs close_t; unreachable rows stay NaN
        c48 = np.full(n, np.nan)
        if n > LABEL_HORIZON:
            c48[: n - LABEL_HORIZON] = close[LABEL_HORIZON:]
        mask = ~resolved
        up_to = mask & (c48 > close)
        dn_to = mask & np.isfinite(c48) & ~(c48 > close)
        lab[up_to] = "up"
        lab[dn_to] = "dn"

        dataframe["&-tb"] = lab
        return dataframe

    # ----------------------------------------------------------------- pipeline
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # atr14 must exist in the SIMULATION dataframe on every path: when FreqAI
        # reuses cached predictions it skips full-dataframe feature population, so
        # a column added only inside feature_engineering_standard would be absent
        # and every barrier callback would KeyError (swallowed per-call => trades
        # without barriers). Computing it here is idempotent (raw column, no "%"
        # prefix, not a feature; feature_engineering_standard recomputes the same
        # values) and changes no model input or prediction.
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        if "up" not in df.columns:
            return df
        long_cond = (df["do_predict"] == 1) & (df["up"] >= 0.5 + FAI_THRESHOLD)
        short_cond = (df["do_predict"] == 1) & (df["up"] <= 0.5 - FAI_THRESHOLD)
        df.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "fai_long")
        df.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "fai_short")
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        # no signal exits (pre-registered); explicit zero columns so the engine
        # always sees them and falls through to custom_exit each candle
        if "exit_long" not in df.columns:
            df["exit_long"] = 0
        if "exit_short" not in df.columns:
            df["exit_short"] = 0
        return df

    # ------------------------------------------------------- barrier exits
    def _entry_atr(self, pair: str, trade) -> float | None:
        """ATR14 of the entry signal candle (last candle closed at/just before fill)."""
        cached = trade.get_custom_data("atr_entry")
        if cached is not None:
            return float(cached)
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or df.empty:
            return None
        sig = df.loc[df["date"] < trade.open_date_utc.replace(tzinfo=timezone.utc)]
        if sig.empty:
            return None
        atr = float(sig.iloc[-1]["atr14"])
        if np.isfinite(atr) and atr > 0:
            trade.set_custom_data("atr_entry", atr)
            return atr
        return None

    def custom_stoploss(
        self, pair: str, trade, current_time: datetime, current_rate: float,
        current_profit: float, after_fill: bool, **kwargs,
    ) -> float | None:
        """Pin a fixed stop at entry-reference close -/+ 2*ATR14 (barrier mirror)."""
        stop_price = trade.get_custom_data("stop_price")
        if stop_price is None:
            atr = self._entry_atr(pair, trade)
            if atr is None:
                return None  # keep default until ATR known
            ref = trade.open_rate  # fill price ~ signal candle close (disclosed approx)
            stop_price = ref - LABEL_ATR_MULT * atr if not trade.is_short else ref + LABEL_ATR_MULT * atr
            trade.set_custom_data("stop_price", float(stop_price))
        stop_price = float(stop_price)
        if not trade.is_short and stop_price >= current_rate:
            return None  # stop above price: cannot express; skip this call
        if trade.is_short and stop_price <= current_rate:
            return None
        return stop_price / current_rate - 1.0

    def custom_exit(
        self, pair: str, trade, current_time: datetime, current_rate: float,
        current_profit: float, **kwargs,
    ) -> str | bool | None:
        # hard timeout at +48h from open (== 48 bars after signal close)
        if current_time - trade.open_date_utc >= timedelta(hours=LABEL_HORIZON):
            return "tb_timeout"
        # take-profit barrier: +2*ATR14 from entry reference
        atr = self._entry_atr(pair, trade)
        if atr is None:
            return None
        ref = trade.open_rate
        if not trade.is_short and current_rate >= ref + LABEL_ATR_MULT * atr:
            return "tb_tp"
        if trade.is_short and current_rate <= ref - LABEL_ATR_MULT * atr:
            return "tb_tp"
        return None
