# BULL diagnostic 1: gate timing decomposition for 2022-2024 re-entry.
# Pure daily-data analysis, no backtests. Causal convention copied from the
# frozen strategy: known = daily close shifted 1 day; gate uses known values.
import pandas as pd
import pathlib

FEATHER_DIR = pathlib.Path("/Users/caihaohan/Code/freqtrade-futures-lab/user_data/data/binance/futures")

def load_1d(base):
    f = FEATHER_DIR / f"{base}_USDT_USDT-1d-futures.feather"
    d = pd.read_feather(f)
    d["date"] = pd.to_datetime(d["date"], utc=True)
    return d.set_index("date")["close"]

closes = pd.DataFrame({b: load_1d(b) for b in ["BTC", "ETH", "SOL"]}).sort_index()
known = closes.shift(1)  # causal: yesterday's close

btc = known["BTC"]
sma100 = btc.rolling(100).mean()
sma50 = btc.rolling(50).mean()
sma20 = btc.rolling(20).mean()

ron_frozen = btc > sma100 * 1.03          # frozen B gate (tol -0.03)
ron_sma100 = btc > sma100                 # V1 ladder half-state
ron_fast50 = btc > sma50                  # fast-confirm candidate
ron_fast20 = btc > sma20

# per-coin SMA50 gate
trend_ok = known > known.rolling(50).mean()

def first_date_after(mask, start, end):
    m = mask.loc[start:end]
    m = m[m]
    return m.index[0] if len(m) else None

def hold_frac(mask, start, end):
    return mask.loc[start:end].mean()

print("=== regime gate first-ON dates (causal, known=shift1) ===")
for label, mask in [("BTC>SMA100x1.03 (frozen)", ron_frozen),
                    ("BTC>SMA100           ", ron_sma100),
                    ("BTC>SMA50            ", ron_fast50),
                    ("BTC>SMA20            ", ron_fast20)]:
    print(f"{label} 2023 first ON: {first_date_after(mask,'2023-01-01','2023-12-31')}")

print("\n=== 2022 sanity: how often would each gate be ON in 2022 (the fake-breakout year)? ===")
for label, mask in [("BTC>SMA100x1.03", ron_frozen), ("BTC>SMA100", ron_sma100),
                    ("BTC>SMA50", ron_fast50), ("BTC>SMA20", ron_fast20)]:
    # first ON + total ON days in 2022
    fd = first_date_after(mask, "2022-01-01", "2022-12-31")
    n = int(mask.loc["2022"].sum())
    print(f"{label}: 2022 ON days={n:3d}/365, first={fd}")

print("\n=== per-coin SMA50 trend gate first-ON in 2023 ===")
for c in ["BTC", "ETH", "SOL"]:
    print(f"{c} > own SMA50 first 2023 ON: {first_date_after(trend_ok[c],'2023-01-01','2023-12-31')}")

print("\n=== full frozen-B membership (ron AND coin SMA50), 2022-2024 ===")
for c in ["BTC", "ETH", "SOL"]:
    memb = ron_frozen & trend_ok[c]
    print(f"{c}: 2022 ON={int(memb.loc['2022'].sum())}d  2023 ON={int(memb.loc['2023'].sum())}d  2024 ON={int(memb.loc['2024'].sum())}d  first2023={first_date_after(memb,'2023-01-01','2023-12-31')}")

print("\n=== monthly regime state 2023 (1=ON) ===")
mon = pd.DataFrame({
    "frozen x1.03": ron_frozen, "sma100": ron_sma100, "sma50": ron_fast50,
}).loc["2022-06":"2024-03"]
print(mon.groupby(mon.index.to_period("M")).mean().round(2).to_string())

print("\n=== equal-weight 3-coin daily return during gate gaps (2023) ===")
ew_ret = closes.pct_change().mean(axis=1)
def cumret(start, end):
    return float(closes.loc[end].div(closes.loc[start]).sub(1).mean())

f_frozen = first_date_after(ron_frozen, "2023-01-01", "2023-12-31")
f_sma100 = first_date_after(ron_sma100, "2023-01-01", "2023-12-31")
f_sma50 = first_date_after(ron_fast50, "2023-01-01", "2023-12-31")
f_eth = first_date_after(trend_ok["ETH"], "2023-01-01", "2023-12-31")
f_sol = first_date_after(trend_ok["SOL"], "2023-01-01", "2023-12-31")
print("year-start 2023-01-01 ew level vs key dates:")
for lab, dt in [("sma50 cross", f_sma50), ("sma100 cross", f_sma100), ("sma100x1.03 (frozen ON)", f_frozen),
                ("ETH sma50", f_eth), ("SOL sma50", f_sol)]:
    print(f"  {lab:24s} {dt}   ew basket cumret 01-01->{dt}: {cumret('2023-01-01', dt):+.1%}")

print("\n=== 2024: was gate already ON at year start? ===")
for label, mask in [("frozen x1.03", ron_frozen), ("sma100", ron_sma100)]:
    print(f"{label}: 2023-12-29 state={bool(mask.loc['2023-12-29'])}, 2024 ON days={int(mask.loc['2024'].sum())}/366")

print("\n=== gap close: last risk-off day before first ON (frozen) ===")
pre = ron_frozen.loc[:"2023-01-12"].iloc[:-1]
last_off = pre[~pre].index[-1]
off_run = ron_frozen.loc["2022-01-01":"2023-01-12"]
off_run = off_run[~off_run]
print(f"frozen ON {f_frozen}; last ON before that: {off_run.index[-1]} -> OFF streak {(f_frozen - off_run.index[-1]).days} days")

# ---- where exactly did x1.03 sit OUT while sma100 stayed IN, and what did it cost? ----
print("\n=== 2023 days where sma100-ON but frozen-x1.03-OFF: cost of the +3% buffer ===")
gap = ron_sma100 & ~ron_frozen
g = gap.loc["2023"]
print(f"gap days 2023: {int(g.sum())}")
ew = closes.pct_change().mean(axis=1).loc["2023"]
print(f"ew basket mean daily ret on gap days: {ew[g].mean():+.3%} vs all-2023 days {ew.mean():+.3%}")
for period, (a, b) in {"May-Jul": ("2023-05-01","2023-07-31"), "Aug-Oct": ("2023-08-01","2023-10-31")}.items():
    gg = gap.loc[a:b]
    if gg.sum():
        print(f"  {period}: {int(gg.sum())} gap days, ew ret those days sum {ew.loc[a:b][gg].sum():+.2%}")

print("\n=== days ron_sma100 OFF entirely (both ladders out), 2023 ===")
both_off = ~ron_sma100
for period, (a, b) in {"Jan-Apr": ("2023-01-01","2023-04-30"), "May-Jul": ("2023-05-01","2023-07-31"), "Aug-Oct": ("2023-08-01","2023-10-31"), "Nov-Dec": ("2023-11-01","2023-12-31")}.items():
    bo = both_off.loc[a:b]
    print(f"  {period}: {int(bo.sum())} OFF days, ew ret those days sum {ew.loc[a:b][bo].sum():+.2%}")

# per-coin sma50 gate gaps on top of regime
print("\n=== 2023: regime x1.03 ON but coin below own SMA50 (SMA50 gate kept coin out) ===")
for c in ["BTC", "ETH", "SOL"]:
    cg = ron_frozen & ~trend_ok[c]
    cg = cg.loc["2023"]
    cew = closes[c].pct_change().loc["2023"]
    print(f"  {c}: {int(cg.sum())} days blocked, {c} ret those days sum {cew[cg].sum():+.2%}")

# SMA50 fast gate 2022 damage estimate
print("\n=== 2022 damage probe for fast-confirm (BTC>SMA50) vs frozen ===")
ew22 = closes.pct_change().mean(axis=1).loc["2022"]
on50 = ron_fast50 & trend_ok.mean(axis=1).astype(bool)  # rough: all coins above own sma50
# proper: per-coin
for c in ["BTC","ETH","SOL"]:
    m = (ron_fast50 & trend_ok[c]).loc["2022"]
    r = closes[c].pct_change().loc["2022"]
    print(f"  {c}: fast50+coin-sma50 ON {int(m.sum())}d 2022, {c} ret those days sum {r[m].sum():+.2%}")
m = (ron_frozen).loc["2022"]
print(f"  (frozen regime ON {int(m.sum())}d 2022)")
