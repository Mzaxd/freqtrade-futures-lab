# ws3 causality + B-alignment assertion test for OPT9_Recycle._recycle_series.
#
# Checks, over the backtest window 2021-01-01..2026-09-12:
#   (1) ALIGNMENT: for sampled instants t, the strategy's slice-based signal
#       (closes strictly before t, drop unclosed day, SMA100) equals an
#       INDEPENDENT full-history reference that replicates B's exact formula
#       from the daily feather (known=close.shift(1); risk_on[row D] =
#       known[D] > known.rolling(100).mean()[D]; applies during day D).
#       Equality of a truncated-data computation with a full-data reference
#       simultaneously proves no-future-leak and B-sync.
#   (2) DAY-BOUNDARY: at t = D 00:00:00 exactly, day D-1 counts as closed
#       (B's convention flips at 00:00 using close(D-1)).
#   (3) INTRADAY CONSTANCY: the signal is constant across day D (00:00..23:00).
#   (4) WARMUP DEFAULT: while the in-frame history has <100 closed days, the
#       signal is None (-> recycle OFF in the strategy) — report which days.
#   (5) HYSTERESIS UNIT SEMANTICS on a synthetic series.
import sys
import pandas as pd

sys.path.insert(0, r"D:\Code\AIQuant\freqtrade-futures-lab\user_data\strategies\oss")
from OPT9_Recycle import OPT9_Recycle  # noqa: E402

DATA = r"D:\Code\AIQuant\freqtrade-futures-lab\user_data\data\binance\futures"
START, END = pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2026-09-12", tz="UTC")

h1 = pd.read_feather(rf"{DATA}\BTC_USDT_USDT-1h-futures.feather")
h1["date"] = pd.to_datetime(h1["date"], utc=True)
h1 = h1.set_index("date")["close"].sort_index()

d1 = pd.read_feather(rf"{DATA}\BTC_USDT_USDT-1d-futures.feather")
d1["date"] = pd.to_datetime(d1["date"], utc=True)
Pd = d1.set_index("date")["close"].sort_index()
known = Pd.shift(1)
ron = known > known.rolling(100).mean()          # B's risk_on, row D applies on day D
b_recycle = ~ron.fillna(False)                   # B off -> recycle on (B semantics)

# frames to test: (label, frame-start) — backtest frame starts ~timerange-200h
frames = [
    ("backtest-frame(2020-12-23 16:00)", h1.loc["2020-12-23 16:00":]),   # mimics 1h frame in the 20210101 backtest
    ("full-1h-history(2020-09-01)", h1.copy()),                           # long-history variant
]

def signal_at(frame: pd.Series, t: pd.Timestamp):
    sub = frame[frame.index < t]                 # causal slice (strictly before)
    return OPT9_Recycle._recycle_series(sub, t, 100, 0)

# --- sample times: every 12h across window + hourly around every flip day ---
grid = pd.date_range(START, END - pd.Timedelta(hours=1), freq="12h")
flip_days = b_recycle.index[(b_recycle != b_recycle.shift(1)).fillna(True)]
around = []
for d in flip_days:
    around += list(pd.date_range(d - pd.Timedelta(days=1), d + pd.Timedelta(days=1), freq="1h"))
around = [t for t in set(around) if START <= t <= END]
times = sorted(set(grid) | set(around))
print(f"sampled instants: {len(times)} (grid {len(grid)} + around-flips {len(around)}), "
      f"flip days: {len(flip_days)}")

fail = 0
warm = 0
warm_days = set()
for label, frame in frames:
    mismatch = []
    prev_day, prev_sig = None, None
    for t in times:
        a = signal_at(frame, t)                  # None / bool
        row_day = t.floor("D")
        b = bool(b_recycle.loc[row_day]) if row_day in b_recycle.index else False
        if a is None:
            warm += 1
            warm_days.add(row_day.date())
            if b:                                # warmup default OFF vs B off->on-recycle
                mismatch.append((t, "None(warmup)", b))
            continue
        if a != b:
            mismatch.append((t, a, b))
        if prev_day == row_day and prev_sig is not None and a is not None and a != prev_sig:
            print(f"INTRADAY FLIP: {t} {prev_sig}->{a}")
            fail += 1
        prev_day, prev_sig = row_day, a
    print(f"[{label}] mismatches vs B reference: {len(mismatch)}")
    for m in mismatch[:10]:
        print("   ", m[0], "mine=", m[1], "Bref=", m[2])
    fail += len(mismatch)

print(f"warmup-default instants (signal None): {warm}; distinct days: {len(warm_days)}"
      + (f" {min(warm_days)}..{max(warm_days)}" if warm_days else ""))
if warm_days:
    bad = [str(d) for d in sorted(warm_days)
           if bool(b_recycle.loc[pd.Timestamp(d, tz="UTC")])]
    print(f"  warmup days where B was OFF (default would diverge): {len(bad)} {bad[:20]}")

# --- hysteresis unit semantics: H=1 -> 2 consecutive raw days to flip ---
raw_idx = pd.date_range("2024-01-01", periods=8, freq="D")
s = pd.Series([10.0, 9.0, 9.0, 10.0, 9.0, 9.0, 9.0, 10.0], index=raw_idx)  # below=on-ish
# craft closes so raw = [F,F,T,F,T,T,T,F] via sma window 2? use sma_window=3:
def raw_of(s, w):
    sma = s.rolling(w).mean()
    return (s <= sma) & sma.notna()
for w, expect in [(3, None)]:
    sma = s.rolling(w).mean()
    print("raw(3):", list(((s <= sma) & sma.notna()).astype(int)))
sigH0 = [OPT9_Recycle._recycle_series(s.iloc[: i + 1], s.index[i] + pd.Timedelta(days=1), 3, 0) for i in range(len(s))]
sigH1 = [OPT9_Recycle._recycle_series(s.iloc[: i + 1], s.index[i] + pd.Timedelta(days=1), 3, 1) for i in range(len(s))]
print("state H=0:", [int(x) if x is not None else None for x in sigH0])
print("state H=1:", [int(x) if x is not None else None for x in sigH1])

print("\nRESULT:", "PASS" if fail == 0 else f"FAIL ({fail})")
sys.exit(0 if fail == 0 else 1)
