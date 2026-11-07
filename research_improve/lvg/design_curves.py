"""LVG design step 2 (IS ONLY, hard-cut 2023-12-31): baseline sleeve curves
from the two full-window zips, AB70/30 synthesis, and OFFLINE vol-scaling
shape check to anchor pre-registered targets. No 24-26 data is printed.
"""
import io
import zipfile

import numpy as np
import pandas as pd


def wallet_from_zip(zpath: str, strategy: str) -> pd.DataFrame:
    zf = zipfile.ZipFile(zpath)
    name = [n for n in zf.namelist() if n.endswith("_wallet.feather")][0]
    df = pd.read_feather(io.BytesIO(zf.read(name)))
    df = df.set_index("date").sort_index()
    return df[["total_quote"]]


A = wallet_from_zip("user_data/backtest_results/backtest-result-2026-11-07_03-54-11.zip", "ARL_2x")
B = wallet_from_zip("user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip", "OPT2_MomRegime15mLb21")
CUT = "2023-12-31"

Ah = A["total_quote"].resample("h").last().ffill()
Bh = B["total_quote"].resample("h").last().ffill()
A7 = Ah / Ah.iloc[0] * 7000
B3 = Bh / Bh.iloc[0] * 3000
P = (A7 + B3).loc[:CUT]

d = P.resample("D").last()
dd30 = (d / d.rolling(30).max() - 1)
yr = d.groupby(d.index.year)
yearly = (yr.last() / yr.first() - 1) * 100
print("=== baseline AB70/30 IS yearly % (starts at calendar-year first daily value) ===")
print(yearly.round(1))
print("maxdd(full IS curve): %.1f%%  dd30 min: %.1f%%" % (((d / d.cummax() - 1).min() * 100), (dd30.min() * 100)))

# sleeve-level IS yearly
for nm, s in (("A7", A7), ("B3", B3)):
    dd = s.resample("D").last().loc[:CUT]
    g = dd.groupby(dd.index.year)
    print(nm, (g.last() / g.first() - 1).mul(100).round(1).to_dict())

# daily returns of the baseline portfolio (IS only)
r = d.pct_change().dropna()
rv30_p = r.rolling(30).std() * np.sqrt(365) * 100  # portfolio realized vol, annualized %
print("\nportfolio RV30 IS yearly median:", rv30_p.groupby(rv30_p.index.year).median().round(1).to_dict())

print("\n=== offline equal-vol scaling of baseline AB70/30 (IS shape only) ===")
print("m_t = clamp(T/RV30_p(t-1), lo, hi); r_scaled(t) = r(t)*m(t-1)")


def vol_scale(ret: pd.Series, T: float, lo: float, hi: float):
    m = (T / ret.rolling(30).std() / np.sqrt(1 / 365) / 100).shift(1).clip(lo, hi)
    rs = ret * m
    eq = (1 + rs.fillna(0)).cumprod()
    return rs, eq, m


for T, lo, hi in [(60, 0.5, 2.0), (45, 0.5, 2.0), (60, 0.75, 1.75), (60, 1.0, 2.0)]:
    rs, eq, m = vol_scale(r, T, lo, hi)
    g = eq.groupby(eq.index.year)
    yy = (g.last() / g.first() - 1) * 100
    dd = (eq / eq.rolling(30).max() - 1).min() * 100
    print(f"T={T:4.0f} clamp[{lo},{hi}]  yearly: {yy.round(1).to_dict()}  dd30min={dd:6.1f}%  m: med={m.median():.2f} p95={m.quantile(0.95):.2f}")
