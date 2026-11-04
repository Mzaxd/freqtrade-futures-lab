"""r3_os_analysis.py — WS-R3 OS adjudication + portfolio layer.

Inputs (research_chop/results/): R3_os_base_ARL2x.zip, R3_os_R3_C3h_N3_D30.zip,
R3_os_R3_C3p_N3_D30.zip; user_data/logs/mtm_daily_B3.csv;
research_chop/data/regime_1h_{BTC,ETH,SOL}.csv.

1. OS daily curves via dp_mtm (INIT=10000, same reconstruction as A3/B3).
2. Chop/trend day masks: per-pair hourly g2|g4 -> day-level OR -> shift(1)
   (day D uses day D-1's labels, all closed before 00:00 UTC of D);
   universe chop day = ANY of the 3 pairs ON.
3. Adjudication (PRE §4): chop-window subset maxDD improvement >= +5pp;
   trend-window annualized return loss <= 2pp.
4. Portfolio: r_p = 0.7*rA + 0.3*rB (ws2 fixed-weight concat; recycle 1.21
   already inside rA). Metrics: OS maxDD, worst 30d rolling DD.
5. MC block bootstrap (30d blocks, 2000 draws, seed=20261103, joint (rA,rB)
   resampling) -> p95 30dDD; red line: variant worse than baseline > 2pp.
"""
import os
import sys

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, os.path.join(r"D:\Code\AIQuant\freqtrade-futures-lab",
                                "research_deepen", "_dispatcher", "scripts"))
import dp_mtm  # noqa: E402

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, "research_chop", "results")
DATA = os.path.join(ROOT, "research_chop", "data")
INIT = 10000.0
ANN = 365.25
SEED = 20261103
N_MC = 2000
BLOCK = 30
OS_S = pd.Timestamp("2024-01-02", tz="UTC")
OS_E = pd.Timestamp("2026-09-13", tz="UTC")   # dp_mtm end (exclusive last stamp 09-12)

RUNS = {
    "BASE": "R3_os_base_ARL2x.zip",
    "C3h_N3_D30": "R3_os_R3_C3h_N3_D30.zip",
    "C3p_N3_D30": "R3_os_R3_C3p_N3_D30.zip",
}


def maxdd(eq):
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def worst30(eq):
    roll = sliding_window_view(eq, BLOCK).max(axis=1)
    return float((eq[BLOCK - 1:] / roll - 1.0).min())


def ann_return(r, days):
    tot = float(np.prod(1.0 + r))
    return tot ** (ANN / days) - 1.0 if days > 0 else float("nan")


# ---------------------------------------------------------------- 1. curves
curves = {}
for name, zn in RUNS.items():
    deq, diag = dp_mtm.reconstruct_window(os.path.join(RES, zn), OS_S, OS_E)
    curves[name] = deq
    print(f"curve {name}: {deq.index[0].date()}..{deq.index[-1].date()} n={len(deq)} "
          f"end_eq={deq.iloc[-1]:.0f} trades={diag['n_trades']}")

b3 = pd.read_csv(os.path.join(ROOT, "user_data", "logs", "mtm_daily_B3.csv"),
                 index_col=0, parse_dates=True)["eq_B3"]
b3.index = pd.to_datetime(b3.index, utc=True)

rets = {}
for name, deq in curves.items():
    rets[name] = deq.pct_change().iloc[1:]
os_days = rets["BASE"].index
rb_os = b3.pct_change().reindex(os_days).dropna()
common = rb_os.index
for name in rets:
    rets[name] = rets[name].reindex(common)
print(f"common OS return days: {common[0].date()}..{common[-1].date()} n={len(common)}")

# ---------------------------------------------------- 2. chop/trend day masks
lab_all = {}
for p in ("BTC", "ETH", "SOL"):
    lab = pd.read_csv(os.path.join(DATA, f"regime_1h_{p}.csv"),
                      index_col="date", parse_dates=True)
    lab.index = pd.to_datetime(lab.index, utc=True)
    lab_all[p] = lab
day_on = {}
for p, lab in lab_all.items():
    on_h = (lab["g2"] | lab["g4"])
    day_on[p] = on_h.groupby(on_h.index.floor("D")).max()   # OR over the day's hours
day_on = pd.DataFrame(day_on)
any_on = day_on.any(axis=1)
# shift(1): day D regime decided from day D-1 labels
chop = any_on.shift(1).fillna(False)
_day_idx = pd.DatetimeIndex(common.normalize())
chop_os = chop.reindex(_day_idx).fillna(False).astype(bool).values
print(f"OS days n={len(common)}  chop days={chop_os.sum()} ({chop_os.mean():.1%})  "
      f"trend days={(~chop_os).sum()}")

# ------------------------------------------------- 3. adjudication per PRE §4
print("\n== OS adjudication (PRE §4) ==")
rows = []
for name in RUNS:
    r = rets[name].values
    eq = np.cumprod(1 + r)
    dd_full = maxdd(eq)
    # chop-window subset DD
    r_chop = r[chop_os]
    eq_chop = np.cumprod(1 + r_chop)
    dd_chop = maxdd(eq_chop)
    # trend-window annualized return
    r_tr = r[~chop_os]
    ann_tr = ann_return(r_tr, (~chop_os).sum())
    rows.append({"name": name, "total": float(eq[-1] - 1), "maxDD_full": dd_full,
                 "chopDD": dd_chop, "trend_ann": ann_tr, "worst30": worst30(eq)})
t = pd.DataFrame(rows).set_index("name")
base = t.loc["BASE"]
print(t.to_string(float_format=lambda v: f"{v*100:.2f}"))
for name in ("C3h_N3_D30", "C3p_N3_D30"):
    imp = (t.loc[name, "chopDD"] - base["chopDD"]) * 100   # shallower DD = positive improvement
    loss = (base["trend_ann"] - t.loc[name, "trend_ann"]) * 100
    verdict_dd = "PASS" if imp >= 5.0 else "FAIL"
    verdict_tr = "PASS" if loss <= 2.0 else "FAIL"
    print(f"{name}: chop-DD improvement {imp:+.2f}pp ({verdict_dd}, need >=+5pp) | "
          f"trend ann loss {loss:+.2f}pp ({verdict_tr}, need <=2pp)")

# ------------------------------------------------------------ 4. combos 70/30
print("\n== Portfolio layer: 0.7*A' + 0.3*B3, OS window ==")
vb = rb_os.values
combo = {}
for name in RUNS:
    combo[name] = 0.7 * rets[name].values + 0.3 * vb
crows = []
for name, r in combo.items():
    eq = np.cumprod(1 + r)
    crows.append({"name": name, "total": float(eq[-1] - 1), "maxDD": maxdd(eq),
                  "worst30": worst30(eq)})
ct = pd.DataFrame(crows).set_index("name")
print(ct.to_string(float_format=lambda v: f"{v*100:.2f}"))

# ------------------------------------------------------------------- 5. MC
print(f"\n== MC block bootstrap (block={BLOCK}d, {N_MC} draws, seed={SEED}), "
      "joint (rA, rB) resampling ==")
n = len(common)
names = list(RUNS)
rng = np.random.default_rng(SEED)
nblk = int(np.ceil(n / BLOCK))
ofs = np.arange(BLOCK)
min30 = np.zeros((N_MC, len(names)))
for it in range(N_MC):
    st = rng.integers(0, n - BLOCK + 1, nblk)
    pos = (st[:, None] + ofs[None, :]).ravel()[:n]
    a_s, b_s = np.hstack([rets[nm].values[pos][:, None] for nm in names]), vb[pos]
    r_cfg = 0.7 * a_s + 0.3 * b_s[:, None]
    eq_all = np.cumprod(1 + r_cfg, axis=0)
    roll = sliding_window_view(eq_all, BLOCK, axis=0).max(axis=-1)
    dd = eq_all[BLOCK - 1:] / roll - 1.0
    min30[it] = dd.min(axis=0)
p95 = np.percentile(min30, 5, axis=0)
med = np.percentile(min30, 50, axis=0)
print(f"{'combo':14s} {'hist worst30':>13s} {'MC med 30dDD':>13s} {'MC p95 30dDD':>13s} {'vs BASE':>9s} {'redline':>8s}")
for j, nm in enumerate(names):
    delta = (p95[j] - p95[names.index("BASE")]) * 100
    red = "VETO" if delta < -2.0 else "ok"
    print(f"{nm:14s} {ct.loc[nm,'worst30']*100:13.2f} {med[j]*100:13.2f} {p95[j]*100:13.2f} "
          f"{delta:+9.2f} {red:>8s}")

# ------------------------------------------------- 6. per-pair gate occupancy
print("\n== OS chop-day mask per pair (reference) ==")
for p in day_on:
    m = day_on[p].shift(1).reindex(_day_idx)
    print(f"  {p}: ON days {int(m.fillna(False).sum())} / {len(common)}")

# save curves for the report
out = pd.DataFrame({k: v for k, v in rets.items()})
out["rB3"] = vb
out["chop_day"] = chop_os
out.to_csv(os.path.join(ROOT, "research_chop", "logs", "r3_os_daily_returns.csv"))
print("\nsaved research_chop/logs/r3_os_daily_returns.csv")
