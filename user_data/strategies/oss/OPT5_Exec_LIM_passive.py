# OPT5 door-2 variant LIM-passive: entry order = LIMIT at the signal candle's
# close (fully passive — fills only if the next 1h candle retraces to that
# price; unfilledtimeout=10min cancels it at the next candle otherwise).
#
# Backtest semantics (freqtrade 2026.8, verified against source):
#   * custom_entry_price is called at the open of candle i for a signal on
#     candle i-1; the signal candle's close is obtained via the same
#     searchsorted(current_time)-1 helper OPT1 uses (causal in backtest and
#     dry-run alike).
#   * The backtester clamps the returned price into candle i's range
#     (long: min(price, high_i)) so a passive long limit can never be
#     marketable above the current high; fills happen at the limit price iff
#     low_i <= price <= high_i.
#   * The backtest fee stays 0.05% taker for both order types — the maker
#     saving is NOT credited here (disclosed in the report; A/B in dry-run).
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class OPT5_Exec_LIM_passive(OPT4_VolatilitySystem):
    entry_premium = 0.0  # passive: exactly the signal close

    order_types = {
        "entry": "limit",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    def custom_entry_price(self, pair: str, trade, current_time, proposed_rate: float,
                           entry_tag, side: str, **kwargs):
        try:
            df, idx = self._signal_candle(pair, current_time)
            if idx < 0:
                return None
            close = float(df.iloc[idx]["close"])
        except Exception:
            return None
        if not close or close <= 0:
            return None
        if side == "short":
            return close * (1.0 - self.entry_premium)
        return close * (1.0 + self.entry_premium)
