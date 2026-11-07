"""LVG design step 1 (IS only): BTC RV30 stats to anchor vol-target grid.

RV30_t = std of the last 30 FULLY CLOSED daily log returns of BTC,
annualized by sqrt(365), in percent. Evaluated at the close of each day D
using days D-30..D-1 (strictly causal; equivalent to a 1-day shift).
Market data only — no strategy results touched here.
"""
import numpy as np
import pandas as pd

df = pd.read_feather("user_data/data/binance/futures/BTC_USDT_USDT-1d-futures.feather")
df = df.set_index("date").sort_index()
close = df["close"]
r = np.log(close / close.shift(1))
rv30 = r.rolling(30).std() * np.sqrt(365) * 100  # % annualized, known at close of day D
# shift(1): value usable from day D+1 onward (strict causality, spec'd 1-day shift)
rv30_lag = rv30.shift(1)

print("=== BTC RV30 (annualized %, 30d, lagged 1d) — yearly stats ===")
g = rv30_lag.groupby(rv30_lag.index.year)
stats = pd.DataFrame({"median": g.median(), "mean": g.mean(), "min": g.min(), "max": g.max(), "p25": g.quantile(0.25), "p75": g.quantile(0.75)})
print(stats.round(1))

is_mask = (rv30_lag.index >= "2021-01-01") & (rv30_lag.index < "2024-01-01")
print("\nIS 21-23 overall median:", round(rv30_lag[is_mask].median(), 1))
print("IS 21-23 overall mean  :", round(rv30_lag[is_mask].mean(), 1))
print("IS 21-23 p25/p75       :", round(rv30_lag[is_mask].quantile(0.25), 1), round(rv30_lag[is_mask].quantile(0.75), 1))
for y in (2021, 2022, 2023):
    m = (rv30_lag.index.year == y)
    print(y, "median", round(rv30_lag[m].median(), 1), "p25", round(rv30_lag[m].quantile(0.25), 1), "p75", round(rv30_lag[m].quantile(0.75), 1))

# daily granularity by month, recent tail (market structure, CONTEXT §5 already discloses yearly)
print("\n=== monthly medians 2021-2026 ===")
print(rv30_lag.resample("ME").median().round(1).tail(24).to_string())
