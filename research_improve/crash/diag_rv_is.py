"""CRASH IS-only diagnostic: BTC RV30 distribution 2021-2023 (strictly <= 2023-12-31).

RV30 definition (frozen for this program):
  hourly log returns of BTC 1h close (feather, full history);
  RV30[t] = std(last 720 hourly log returns up to and including hour t) * sqrt(24*365)
  daily RV30 series = RV30 sampled at the LAST hour of each UTC day (day fully closed).

Outputs (to stdout + JSON beside this script):
  - quantiles of daily RV30 over 2021-2023 (p50/p75/p85/p90/p95)
  - same for trailing-365d-rank calibration sanity: how many days >= p85 value
  - per-year quantiles so we can see regime drift WITHIN IS only.

NO 2024+ data is read: the feather is sliced at 2023-12-31 before any output.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FEATHER = HERE.parent.parent / "user_data" / "data" / "binance" / "futures" / "BTC_USDT_USDT-1h-futures.feather"
CUT = pd.Timestamp("2024-01-01", tz="UTC")  # exclusive upper bound — IS only

df = pd.read_feather(FEATHER)[["date", "close"]]
df["date"] = pd.to_datetime(df["date"], utc=True)
df = df[df["date"] < CUT].reset_index(drop=True)

rets = np.log(df["close"]).diff()
rv30 = rets.rolling(720).std() * np.sqrt(24 * 365)
s = pd.DataFrame({"date": df["date"], "rv30": rv30}).dropna()
# daily sample: last fully closed UTC day per bin
s["day"] = s["date"].dt.floor("1D")
daily = s.groupby("day").last()["rv30"]

daily_is = daily[daily.index >= pd.Timestamp("2021-01-01", tz="UTC")]
q = daily_is.quantile([0.50, 0.75, 0.85, 0.90, 0.95])
print("BTC daily RV30 (annualized, from 1h rets, 720h window), 2021-2023:")
print(q.to_string())
print(f"days in sample: {len(daily_is)}, min {daily_is.min():.4f}, max {daily_is.max():.4f}")

years = daily_is.index.year
for yr in (2021, 2022, 2023):
    sub = daily_is[years == yr]
    print(f"{yr}: p50 {sub.quantile(.5):.3f}  p85 {sub.quantile(.85):.3f}  max {sub.max():.3f}")

out = {
    "cut": str(CUT),
    "n_days": int(len(daily_is)),
    "quantiles": {str(k): float(v) for k, v in q.items()},
    "yearly": {
        str(y): {
            "p50": float(daily_is[years == y].quantile(0.5)),
            "p85": float(daily_is[years == y].quantile(0.85)),
            "max": float(daily_is[years == y].max()),
        }
        for y in (2021, 2022, 2023)
    },
}
(HERE / "rv_is_stats.json").write_text(json.dumps(out, indent=2))
print("\nwrote", HERE / "rv_is_stats.json")
