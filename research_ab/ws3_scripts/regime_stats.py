# ws3 regime stats — replicate OPT1_MomRegime15mFast's BTC<SMA100 risk_on signal
# from the daily feather (B's own data path) and characterize crossings 2021-2026.
import pandas as pd

FEATHER = r"D:\Code\AIQuant\freqtrade-futures-lab\user_data\data\binance\futures\BTC_USDT_USDT-1d-futures.feather"
START, END = "2021-01-01", "2026-09-12"   # backtest window

d = pd.read_feather(FEATHER)
d["date"] = pd.to_datetime(d["date"], utc=True)
Pd = d.set_index("date")["close"].sort_index()

# B's exact computation (OPT1_MomRegime15mFast._compute_xs):
#   known = Pd.shift(1); ron_d[row D] = known[D] > known.rolling(100).mean()[D]
# i.e. on day D (intraday), B compares close(D-1) vs SMA100 over closes D-100..D-1.
known = Pd.shift(1)
sma = known.rolling(100).mean()
ron_d = known > sma * (1.0 - 0.0)          # REGIME_TOLERANCE = 0.0

# risk_on active on intraday day D = ron_d at row D
risk_on = ron_d.copy()
risk_on.index = risk_on.index              # row date == intraday day it applies to

win = risk_on.loc[START:END]
print(f"days in window: {len(win)}  (NaN sma -> False via B's fillna(False))")
print(f"  risk_on days : {int(win.fillna(False).sum())}")
print(f"  risk_off days: {int((~win.fillna(False)).sum())}  -> recycle-eligible day share: "
      f"{(~win.fillna(False)).mean():.3f}")

# NaN warmup inside window?
nan_days = win[win.isna()]
print(f"  NaN (no SMA yet) days inside window: {len(nan_days)}"
      + (f"  {nan_days.index.min().date()}..{nan_days.index.max().date()}" if len(nan_days) else ""))

# B regime during MY warmup window (backtest 1h data starts ~2020-12-23; SMA100 from
# in-frame resample first valid ~2021-04-02; before that OPT9_Recycle defaults OFF)
mywarm = risk_on.loc["2021-01-01":"2021-04-02"]
print(f"\nB risk_on during OPT9_Recycle 1h-warmup 2021-01-01..2021-04-02: "
      f"on={int(mywarm.fillna(False).sum())}/{len(mywarm)} days, off={int((~mywarm.fillna(False)).sum())}")
if (~mywarm.fillna(False)).any():
    print("  OFF days:", [str(x.date()) for x in mywarm.fillna(False)[~mywarm.fillna(False)].index])

# crossings of the raw daily condition within window (on the day-boundary series)
raw = win.fillna(False).astype(bool)
flips = raw != raw.shift(1)
flip_days = raw.index[flips]
print(f"\nraw condition flips (risk_on<->off) at day boundary: {(flips.sum()-0)}")
print(f"distinct regime segments: {(raw != raw.shift(1)).cumsum().nunique()}")

seg_id = (raw != raw.shift(1)).cumsum()
segs = []
for sid, g in raw.groupby(seg_id):
    segs.append((g.index[0], g.index[-1], bool(g.iloc[0]), len(g)))
segs.sort()
print(f"{'start':<12}{'end':<12}{'state':<7}{'days':>5}")
for s in segs:
    print(f"{str(s[0].date()):<12}{str(s[1].date()):<12}{'ON' if s[2] else 'OFF':<7}{s[3]:>5}")

# isolated flips: segments shorter than N days (1-3 day whipsaws)
short_off = [s for s in segs if not s[2] and s[3] <= 3]
short_on = [s for s in segs if s[2] and s[3] <= 3]
print(f"\nOFF segments <=3 days (isolated): {len(short_off)} -> {[(str(s[0].date()), s[3]) for s in short_off]}")
print(f"ON segments <=3 days (isolated) : {len(short_on)} -> {[(str(s[0].date()), s[3]) for s in short_on]}")

# distance-to-SMA on flip days (how marginal are the crossings?)
dist = (known / sma - 1.0).loc[START:END]
flip_dist = dist[flips & dist.notna()]
print(f"\n|close/sma-1| on flip days: min={flip_dist.abs().min():.5f} "
      f"median={flip_dist.abs().median():.4f} max={flip_dist.abs().max():.4f}")

# bear-state share per year (recycle day share)
print("\nper-year OFF-day share (raw condition):")
for y in range(2021, 2027):
    wy = raw.loc[f"{y}"]
    if len(wy):
        print(f"  {y}: {int((~wy).sum()):>4}/{len(wy)} = {(~wy).mean():.3f}")
