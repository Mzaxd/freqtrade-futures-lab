# type: ignore
# pylint: disable=import-error
"""NC_FundingCarry — Agent C adaptation of nateemma/strategies Funding/FundingCarry.py
for freqtrade 2026.8 + Binance USDT perpetual futures (BTC/ETH/SOL whitelist).

Adaptation notes (signal logic unchanged):
  * class renamed to NC_FundingCarry
  * funding history: repo expected `<repo>/data/funding/<BASE>_funding.feather` with
    columns (dt, funding); this lab has freqtrade-downloaded Binance USDT-perp funding
    feathers at user_data/data/binance/futures/<BASE>_USDT_USDT-1h-funding_rate.feather
    with columns (date, funding_rate) -> path + column mapping adapted
  * BTC informative / regime reference pair: "BTC/USDT" -> "BTC/USDT:USDT" (futures)
  * long-only spot -> futures (can_short False). NB: on perps the backtest now also
    books funding payments while holding, which the original spot run never paid.

Original signal: enter long when trailing funding z-score < -1.5 (crowded shorts),
gated by BTC > 500h SMA (~21d) circuit breaker; patient pure-time exit at 16h;
no ROI / no stop (validated design). Claimed (repo, BinanceUS spot with liquidity
caps, 2024-2026): +6.6% total / Sharpe 0.89 (down from phantom +23.7%).
"""
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd
from freqtrade.strategy import IStrategy


logger = logging.getLogger(__name__)

# Agent C: lab futures funding feathers (freqtrade download-data format)
FUND_DIR = Path(__file__).resolve().parents[2] / "data" / "binance" / "futures"


class NC_FundingCarry(IStrategy):
    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 550   # cover the MARKET_SMA window

    # --- exit stack: patient pure-time-exit tuned to the 8-24h funding horizon ---
    minimal_roi = {"0": 10.0}    # OFF
    stoploss = -0.99             # OFF
    use_custom_stoploss = False
    trailing_stop = False

    # --- tunables ---
    ENTRY_Z = -1.5       # enter long when trailing funding z-score < this (crowded shorts)
    FUND_WIN = 90        # trailing settlements (~30d at 8h) for the z-score
    MAX_HOLD_H = 16      # time-exit cap; 12-24h is a robust plateau
    BREAKER_ENABLE = True
    MARKET_SMA = 500     # BTC ~21d SMA — down-market circuit-breaker
    REGIME_REF = "BTC/USDT:USDT"   # Agent C: futures pair format

    # --- liquidity-aware sizing ---
    MIN_QUOTE_VOLUME = 1000
    QUOTE_VOLUME_HEADROOM_MULT = 10.0

    def _funding_z(self, pair: str, dates: pd.Series) -> pd.Series:
        base = pair.split(":")[0].split("/")[0]
        fpath = FUND_DIR / f"{base}_USDT_USDT-1h-funding_rate.feather"
        if not fpath.exists():
            return pd.Series(0.0, index=dates.index)
        f = pd.read_feather(fpath)
        # Agent C: freqtrade funding feather columns (date, funding_rate) -> repo (dt, funding)
        f = f.rename(columns={"date": "dt", "funding_rate": "funding"})
        f["dt"] = pd.to_datetime(f["dt"], utc=True)
        f = f.sort_values("dt").reset_index(drop=True)
        m = f["funding"].rolling(self.FUND_WIN, min_periods=10).mean()
        s = f["funding"].rolling(self.FUND_WIN, min_periods=10).std()
        f["fz"] = ((f["funding"] - m) / s).fillna(0.0)
        left = pd.DataFrame({"date": pd.to_datetime(dates, utc=True)})
        merged = pd.merge_asof(
            left.sort_values("date"),
            f[["dt", "fz"]].rename(columns={"dt": "date"}).sort_values("date"),
            on="date", direction="backward",
        )
        return merged["fz"].fillna(0.0)

    def informative_pairs(self):
        return [(self.REGIME_REF, self.timeframe)] if self.BREAKER_ENABLE else []

    def _market_risk_on(self, dataframe: pd.DataFrame) -> pd.Series:
        if not self.BREAKER_ENABLE:
            return pd.Series(1, index=dataframe.index)
        btc = self.dp.get_pair_dataframe(self.REGIME_REF, self.timeframe)
        if btc is None or len(btc) == 0:
            return pd.Series(1, index=dataframe.index)
        btc = btc.copy()
        btc["risk_on"] = (
            btc["close"] > btc["close"].rolling(self.MARKET_SMA, min_periods=24).mean()
        ).astype(int)
        btc["date"] = pd.to_datetime(btc["date"], utc=True)
        left = dataframe.copy(); left["date"] = pd.to_datetime(left["date"], utc=True)
        m = pd.merge_asof(
            left[["date"]].sort_values("date"),
            btc[["date", "risk_on"]].sort_values("date"),
            on="date", direction="backward",
        )
        return pd.Series(m["risk_on"].fillna(1).values, index=dataframe.index)

    def populate_indicators(self, dataframe, metadata):
        dataframe["funding_z"] = self._funding_z(metadata["pair"], dataframe["date"]).values
        dataframe["risk_on"] = self._market_risk_on(dataframe).values
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["funding_z"] < self.ENTRY_Z)
            & (dataframe["risk_on"] == 1)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        return dataframe  # exits via time (custom_exit); ROI/stop off

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        held_h = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        if held_h >= self.MAX_HOLD_H:
            return "time_exit"
        return None

    # --- phantom-fill protection (ported from Framework/BaseStrategy) ---
    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        """Cap the stake at <=1/HEADROOM of the candle's quote volume so the order
        doesn't dominate a thin candle."""
        if self.dp.runmode.value in ("plot", "other"):
            return proposed_stake
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        last = df.iloc[-1].squeeze()
        quote_volume = last["volume"] * last["close"]
        fillable = quote_volume / self.QUOTE_VOLUME_HEADROOM_MULT
        return min(proposed_stake, fillable)

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        """Reject if the candle can't absorb the (already-reduced) order with
        headroom, or if it's a dust pair below MIN_QUOTE_VOLUME."""
        if self.dp.runmode.value in ("plot", "other"):
            return True
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        last = df.iloc[-1].squeeze()
        quote_volume = last["volume"] * last["close"]
        required = max(self.MIN_QUOTE_VOLUME, self.QUOTE_VOLUME_HEADROOM_MULT * amount * rate)
        if quote_volume < required:
            logger.info("NC_FundingCarry reject %s: quote_vol %.0f < required %.0f",
                        pair, quote_volume, required)
            return False
        return True
