# BULL diagnostic 2: actual B-sleeve trades/exposure in 2023-2024 vs gate windows;
# exact ON/OFF transitions; deprivation streaks for fast-reentry safety (2022/2025/26).
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
ron_frozen = btc > btc.rolling(100).mean() * 1.03
ron_sma100 = btc > btc.rolling(100).mean()
ron_fast50 = btc > btc.rolling(50).mean()

print("=== frozen regime ON/OFF transitions 2023 (date = first day the CAUSUAL gate is ON) ===")
r = ron_frozen.loc["2022-12-15":"2024-01-05"].astype(int)
sw = r.diff().fillna(r.iloc[0])
for d, v in sw[sw != 0].items():
    print(f"  {d.date()}  {'ON' if v==1 else 'OFF'}")

print("\n=== BTC price at each 2023 transition + ew basket move during OFF windows ===")
ew = closes.pct_change().mean(axis=1)
offs = [d for d, v in sw[sw != 0].items() if v == -1]
ons = [d for d, v in sw[sw != 0].items() if v == 1]
transitions = list(sw[sw != 0].index)
for i, d in enumerate(transitions):
    v = sw.loc[d]
    if v == -1 and i + 1 < len(transitions):
        nxt = transitions[i + 1]
        off_ret = (1 + ew.loc[d:nxt]).prod() - 1
        print(f"  OFF window {d.date()} -> {nxt.date()}: ew basket {off_ret:+.1%}  (BTC {closes['BTC'].loc[nxt]/closes['BTC'].loc[d]-1:+.1%})")

# ---------- deprivation streaks: days since last frozen-ON day ----------
on_days = ron_frozen.fillna(False)
last_on = on_days.cumsum()
day_idx = pd.Series(np.arange(len(on_days)), index=on_days.index)
last_on_idx = day_idx.where(on_days).ffill()          # index of last ON day
deprivation = day_idx - last_on_idx - 1               # days since last ON (0 on ON days)
print("\n=== max deprivation streaks by year (frozen x1.03 ON) ===")
for y in range(2021, 2027):
    dd = deprivation.loc[f"{y}"]
    print(f"  {y}: max={dd.max():.0f}d  (at {dd.idxmax().date()})")

print("\n=== 2022: deprivation level at each BTC>SMA50 upcross (fast-reentry fire check) ===")
# upcross days of sma50
cross = (ron_fast50 & ~ron_fast50.shift(1).fillna(False))
for d in cross.loc["2022"].index:
    print(f"  cross {d.date()}: deprivation={deprivation.loc[d]:.0f}d")
print("  2023:")
for d in cross.loc["2023-01":"2023-03"].index:
    print(f"  cross {d.date()}: deprivation={deprivation.loc[d]:.0f}d")

print("\n=== 2025/2026: frozen regime state + deprivation (OOS risk for fast path) ===")
r25 = ron_frozen.loc["2025"]
print(f"  2025 ON days: {int(r25.sum())}/365; 2026 (to 11-06): {int(ron_frozen.loc['2026'].sum())}/{len(ron_frozen.loc['2026'])}")
r2 = ron_frozen.loc["2024-12-01":].astype(int)
sw2 = r2.diff().fillna(r2.iloc[0])
for d, v in sw2[sw2 != 0].items():
    print(f"  {d.date()} {'ON' if v==1 else 'OFF'}  (deprivation at that point: {deprivation.loc[d]:.0f}d)")
cross26 = cross.loc["2024-12-01":]
for d in cross26.index:
    print(f"  sma50 upcross {d.date()}: deprivation={deprivation.loc[d]:.0f}d")

# ---------- actual B trades from zip ----------
z = zipfile.ZipFile("/Users/caihaohan/Code/freqtrade-futures-lab/user_data/backtest_results/backtest-result-2026-11-07_03-56-10.zip")
j = json.loads(z.read("backtest-result-2026-11-07_03-56-10.json"))
s = j["strategy"]["OPT2_MomRegime15mLb21"]
trades = pd.DataFrame(s["trades"])
trades["open_date"] = pd.to_datetime(trades["open_date"], utc=True)
trades["close_date"] = pd.to_datetime(trades["close_date"], utc=True)
print("\n=== B actual trades touching 2023 (pair, open, close, profit_abs, nr orders) ===")
t23 = trades[(trades["close_date"] >= "2023-01-01") & (trades["open_date"] < "2024-01-01")]
for _, t in t23.iterrows():
    print(f"  {t['pair']:16s} {t['open_date'].date()} -> {t['close_date'].date()}  PnL {t['profit_abs']:8.0f}  orders {len(t['orders'])}")

# exposure reconstruction: position notional over time from orders
rows = []
for _, t in trades.iterrows():
    amt = 0.0
    for o in t["orders"]:
        od = pd.to_datetime(o["order_date"], utc=True)
        ft = o.get("order_filled_timestamp")
        fd = pd.to_datetime(ft, unit="ms", utc=True) if ft else None
        if o["side"] == "buy" and o["status"] in ("closed",):
            pass
    # simpler: use amount series from trade rows later if needed
print("\ntrade count 2023:", len(t23), " profit_abs sum 2023:", t23["profit_abs"].sum())

# wallet feather yearly returns
import io
wf = z.read("backtest-result-2026-11-07_03-56-10_OPT2_MomRegime15mLb21_wallet.feather")
open("/tmp/b_wallet.feather", "wb").write(wf)
w = pd.read_feather("/tmp/b_wallet.feather")
w["date"] = pd.to_datetime(w["date"], utc=True)
w = w.set_index("date")["total_quote"]
d = w.resample("D").last().ffill()
yr = d.groupby(d.index.year)
print("\n=== B wallet daily-curve yearly returns (feather, unanchored end) ===")
for y, g in yr:
    print(f"  {y}: {(g.iloc[-1]/g.iloc[0]-1):+.1%}  (start {g.iloc[0]:.0f} -> end {g.iloc[-1]:.0f})")
print("profit_total_abs anchor:", s["profit_total_abs"], "final_balance:", s["final_balance"])
