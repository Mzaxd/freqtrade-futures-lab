# BULL diagnostic 3: focused numbers (compact output)
import zipfile, json
import pandas as pd
import numpy as np
import pathlib

FEATHER_DIR = pathlib.Path("/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures")

def load_1d(base):
    f = FEATHER_DIR / f"{base}_USDT_USDT-1d-futures.feather"
    d = pd.read_feather(f)
    d["date"] = pd.to_datetime(d["date"], utc=True)
    return d.set_index("date")["close"]

closes = pd.DataFrame({b: load_1d(b) for b in ["BTC", "ETH", "SOL"]}).sort_index()
known = closes.shift(1)
btc = known["BTC"]
sma100 = btc.rolling(100).mean()
ron_frozen = btc > sma100 * 1.03
ron_sma100 = btc > sma100
ron_fast50 = btc > btc.rolling(50).mean()
trend_ok = known > known.rolling(50).mean()

# deprivation
on = ron_frozen.fillna(False)
day_idx = pd.Series(np.arange(len(on)), index=on.index)
last_on_idx = day_idx.where(on).ffill()
dep = (day_idx - last_on_idx - 1).clip(lower=0)  # 0 on ON days, else days since last ON... approximate

cross = (ron_fast50 & ~ron_fast50.shift(1).fillna(False))

print("=== 1) 2022 Sep-2023 Feb sma50 upcrosses with deprivation (fire-check for thr=250) ===")
cs = cross.loc["2022-08-01":"2023-02-10"]
for d in cs[cs].index:
    print(f"  upcross {d.date()} dep={dep.loc[d]:.0f}d")

print("\n=== 2) SOL windows 2023: regime x1.03 ON but SOL below own SMA50, by month ===")
sol_block = (ron_frozen & ~trend_ok["SOL"]).loc["2023"]
sol_ret = closes["SOL"].pct_change().loc["2023"]
print(sol_block.groupby(sol_block.index.month).agg(["sum"]).to_string(header=False) if False else "")
for m in range(1, 13):
    b = sol_block[sol_block.index.month == m]
    if b.sum():
        r = sol_ret.reindex(b.index)
        print(f"  2023-{m:02d}: {int(b.sum())}d blocked, SOL ret sum {r[b].sum():+.2%}")

print("\n=== 3) SOL Oct 2023 daily (the Oct 20-27 window) ===")
sol_t = trend_ok["SOL"].loc["2023-10-15":"2023-11-05"]
ron_t = ron_frozen.loc["2023-10-15":"2023-11-05"]
px = closes["SOL"].loc["2023-10-15":"2023-11-05"]
for d in px.index:
    print(f"  {d.date()} SOL={px[d]:7.1f} ron={int(ron_t[d])} solTrend={int(sol_t[d])}")

print("\n=== 4) 2024 gap days (sma100 ON, x1.03 OFF): ew return (V2 ladder OOS safety, price data only) ===")
gap = (ron_sma100 & ~ron_frozen)
ew = closes.pct_change().mean(axis=1)
g24 = gap.loc["2024"]
print(f"  gap days 2024: {int(g24.sum())}, ew sum {ew[g24].sum():+.2%}")
g25 = gap.loc["2025"]; g26 = gap.loc["2026"]
print(f"  gap days 2025: {int(g25.sum())}, ew sum {ew[g25].sum():+.2%}")
print(f"  gap days 2026: {int(g26.sum())}, ew sum {ew[g26].sum():+.2%}")

print("\n=== 5) per-coin Jan 1 -> Jan 13 2023 (the missed first leg) ===")
for c in ["BTC", "ETH", "SOL"]:
    print(f"  {c}: {closes[c].loc['2023-01-13']/closes[c].loc['2023-01-01']-1:+.1%}")
print("  sma50-cross (Jan 5) levels:", {c: f"{closes[c].loc['2023-01-05']/closes[c].loc['2023-01-01']-1:+.1%}" for c in ['BTC','ETH','SOL']})

# 6) B actual 2023 trades + wallet
z = zipfile.ZipFile("/Users/caihaohan/Code/freqtrade-futures-lab/user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip")
j = json.loads(z.read("backtest-result-2026-11-07_03-56-10.json"))
s = j["strategy"]["OPT2_MomRegime15mLb21"]
trades = pd.DataFrame(s["trades"])
trades["open_date"] = pd.to_datetime(trades["open_date"], utc=True)
trades["close_date"] = pd.to_datetime(trades["close_date"], utc=True)
print("\n=== 6) B trades touching 2023 ===")
t23 = trades[(trades["close_date"] >= "2023-01-01") & (trades["open_date"] < "2024-01-01")]
for _, t in t23.iterrows():
    print(f"  {t['pair']:16s} {str(t['open_date'].date())} -> {str(t['close_date'].date())}  PnL {t['profit_abs']:8.0f}  norders {len(t['orders'])}")
print("  2023 profit_abs sum:", round(t23["profit_abs"].sum()))

w = pd.read_feather("/tmp/b_wallet.feather")
w["date"] = pd.to_datetime(w["date"], utc=True)
w = w.set_index("date")["total_quote"]
d = w.resample("D").last().ffill()
d23 = d.loc["2023"]
print("\n=== B wallet monthly 2023 (start equity ~", round(d23.iloc[0]), ") ===")
mon = d23.groupby(d23.index.to_period("M")).agg(["first", "last"])
for p, row in mon.iterrows():
    print(f"  {p}: {(row['last']/row['first']-1):+.1%}")

# 7) what would ideal exposure have earned per ON/OFF window (attribution sanity)
print("\n=== ew monthly 2023 (market) for reference ===")
ewm = (1 + ew.loc["2023"]).groupby(ew.loc["2023"].index.to_period("M")).prod() - 1
for p, v in ewm.items():
    print(f"  {p}: {v:+.1%}")
