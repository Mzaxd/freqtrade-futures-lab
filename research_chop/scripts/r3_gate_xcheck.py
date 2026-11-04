"""r3_gate_xcheck.py — gate implementation consistency vs C0 labels (PRE §6.2).

1. Entry-time check (strongest): for every trade of the winner IS/OS runs,
   recompute the strategy's exact gate evaluation — raw feather frame cut to
   (window_start - 200 startup candles) like the backtest, searchsorted
   strictly before the entry candle, tail-slice labeling (R3_Gates idiom) —
   and compare g1/g2/g4 against research_chop/data/regime_1h_*.csv at the
   same candle.
2. Calendar-window check: 3+ windows (incl. the disclosed startup partial
   zone Jan-2021 / Jan-2024 and the 2026 bleed window), full hourly series
   comparison vs the CSVs.
3. Sizing behavior check: join baseline vs C3h_N3_D30 IS trades on
   (pair, open_date) -> stakes identical or halved; count halved entries.
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Code\AIQuant\freqtrade-futures-lab")
DATA = ROOT / "user_data" / "data" / "binance" / "futures"
LAB = ROOT / "research_chop" / "data"
sys.path.insert(0, str(ROOT / "research_chop" / "strategies"))
from R3_Gates import _label_tail  # noqa: E402

PAIRS = {"BTC/USDT:USDT": "BTC", "ETH/USDT:USDT": "ETH", "SOL/USDT:USDT": "SOL"}


def load_zip_trades(zn):
    with zipfile.ZipFile(ROOT / "research_chop" / "results" / zn) as f:
        nm = [n for n in f.namelist() if n.endswith(".json") and "config" not in n
              and "market" not in n and "meta" not in n][0]
        d = json.loads(f.read(nm))
    s = list(d["strategy"].values())[0]
    return pd.DataFrame(s["trades"])


raw = {}
lab = {}
for p in PAIRS.values():
    df = pd.read_feather(DATA / f"{p}_USDT_USDT-1h-futures.feather")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    raw[p] = df
    L = pd.read_csv(LAB / f"regime_1h_{p}.csv", index_col="date", parse_dates=True)
    L.index = pd.to_datetime(L.index, utc=True)
    lab[p] = L


def gate_at(pair, ts, frame_start):
    """Strategy-exact evaluation: frame = feather from frame_start; last candle
    strictly before ts; tail-slice label."""
    df = raw[pair]
    df = df[df["date"] >= frame_start]
    idx = int(df["date"].searchsorted(pd.Timestamp(ts).floor("ms"))) - 1
    if idx < 90:
        return None
    return _label_tail(df.iloc[max(0, idx - 800): idx + 1]), df["date"].iloc[idx]


# ---- 1. entry-time check over winner IS + OS runs -------------------------
print("== 1. entry-time gate check (winner R3_C3h_N3_D30; market-gate arms use the same machinery) ==")
for zn, frame_start in [("R3_is_R3_G2h.zip", pd.Timestamp("2020-12-24", tz="UTC")),
                        ("R3_is_R3_G4h.zip", pd.Timestamp("2020-12-24", tz="UTC")),
                        ("R3_os_R3_C3h_N3_D30.zip", pd.Timestamp("2023-12-25", tz="UTC"))]:
    tr = load_zip_trades(zn)
    ok = mismatch = na = 0
    for _, t in tr.iterrows():
        (g1, g2, g4), candle = gate_at(PAIRS[t["pair"]], t["open_date"], frame_start)
        row = lab[PAIRS[t["pair"]]].loc[candle]
        if (g1, g2, g4) == (bool(row["g1"]), bool(row["g2"]), bool(row["g4"])):
            ok += 1
        else:
            mismatch += 1
            if mismatch <= 5:
                print(f"  MISMATCH {t['pair'][:3]} entry {t['open_date'][:16]} candle {candle} "
                      f"strategy=({g1},{g2},{g4}) csv=({bool(row['g1'])},{bool(row['g2'])},{bool(row['g4'])})")
    print(f"  {zn}: entries={len(tr)} match={ok} mismatch={mismatch} na={na}")

# ---- 2. calendar windows ---------------------------------------------------
print("== 2. calendar-window hourly check vs CSV ==")
WINDOWS = [("2021-01-01", "2021-02-01", pd.Timestamp("2020-12-24", tz="UTC"), "IS startup partial zone"),
           ("2022-06-01", "2022-09-01", pd.Timestamp("2020-12-24", tz="UTC"), "2022 bear chop"),
           ("2025-01-01", "2025-04-01", pd.Timestamp("2023-12-25", tz="UTC"), "OS mid window"),
           ("2026-02-15", "2026-04-15", pd.Timestamp("2023-12-25", tz="UTC"), "2026 bleed window"),
           ("2024-01-02", "2024-02-01", pd.Timestamp("2023-12-25", tz="UTC"), "OS startup partial zone")]
for w0, w1, fs, name in WINDOWS:
    for p in ("BTC", "ETH", "SOL"):
        df = raw[p][raw[p]["date"] >= fs]
        sub = df[(df["date"] >= w0) & (df["date"] < w1)]
        bad = 0
        n = 0
        for _, row in sub.iterrows():
            idx = int(df["date"].searchsorted(row["date"])) - 1
            if idx < 90:
                continue
            g = _label_tail(df.iloc[max(0, idx - 800): idx + 1])
            L = lab[p].loc[df["date"].iloc[idx]]
            n += 1
            if g != (bool(L["g1"]), bool(L["g2"]), bool(L["g4"])):
                bad += 1
        print(f"  {name} [{w0}..{w1}] {p}: hours={n} mismatch={bad}")

# ---- 3. sizing behavior check ---------------------------------------------
print("== 3. baseline vs C3h_N3_D30 IS stake comparison ==")
a = load_zip_trades("R3_is_R3_G2h.zip")  # any 207-trade IS run has baseline stakes
a = a[a["pair"] != ""]  # noop keep
base_is = load_zip_trades("R3_os_base_ARL2x.zip")  # placeholder, replaced below
# reload correct baseline IS from the BASE full run sliced to IS entries
base_full = load_zip_trades("R3_base_ARL2x_full.zip")
base_is = base_full[base_full["open_date"] < "2024-01-01"].copy()
var = load_zip_trades("R3_is_R3_C3h_N3_D30.zip")
key = ["pair", "open_date"]
m = base_is.set_index(key)["stake_amount"].to_frame("base").join(
    var.set_index(key)["stake_amount"].to_frame("var"), how="inner")
ratio = m["var"] / m["base"]
halved = (ratio < 0.65).sum()
print(f"  joined trades={len(m)}  halved(~x0.5)={halved}  ratio min/med/max="
      f"{ratio.min():.3f}/{ratio.median():.3f}/{ratio.max():.3f}")
print(f"  entries identical (open dates match): {len(m) == len(var) == 207}")
