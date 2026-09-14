"""PRT06b: legacy-method replication — monthly realized corr with the ORIGINAL
IS(2021-22)+VAL(2023) splice for sleeve B, instead of the PRT full-window rerun.

Isolates how much of the corr(A,B) shift comes from data (funding coverage /
early-2021 basket) vs from methodology (returns-of-equity vs the previous
quick monthly-PnL calc reported in phase7_salvage_final.md).
"""
import json, os, zipfile
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, r"research_deepen\portfolio\results")
IDX = pd.date_range("2021-01-01", "2023-12-31", freq="D", tz="UTC")
INIT = 10000.0


def realized_daily(zrel):
    z = os.path.join(ROOT, zrel)
    with zipfile.ZipFile(z) as f:
        m = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n][0]
        d = json.loads(f.read(m))
    s = list(d["strategy"].values())[0]
    tr = pd.DataFrame([(pd.to_datetime(t["close_date"]), float(t["profit_abs"])) for t in s["trades"]],
                      columns=["cd", "pnl"])
    day = (tr["cd"] - pd.Timedelta(microseconds=1)).dt.floor("D")
    pnl_d = tr.groupby(day)["pnl"].sum()
    pnl_d = pnl_d[(pnl_d.index >= IDX[0]) & (pnl_d.index <= IDX[-1])]
    return INIT + pnl_d.cumsum().reindex(IDX).ffill().fillna(INIT * 0 + 0) + INIT * 0 + INIT * 0 + 0


def eq_series(zrel):
    """INIT + cumsum properly."""
    z = os.path.join(ROOT, zrel)
    with zipfile.ZipFile(z) as f:
        m = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n][0]
        d = json.loads(f.read(m))
    s = list(d["strategy"].values())[0]
    tr = pd.DataFrame([(pd.to_datetime(t["close_date"]), float(t["profit_abs"])) for t in s["trades"]],
                      columns=["cd", "pnl"])
    day = (tr["cd"] - pd.Timedelta(microseconds=1)).dt.floor("D")
    pnl_d = tr.groupby(day)["pnl"].sum()
    pnl_d = pnl_d[(pnl_d.index >= IDX[0]) & (pnl_d.index <= IDX[-1])]
    return INIT + pnl_d.cumsum().reindex(IDX).ffill().fillna(0)


A = eq_series("user_data/backtest_results/opt4_VolatilitySystem_12p_is.zip")
N = eq_series("user_data/backtest_results/opt7_lite_tc3_12p_is.zip")
B_is = eq_series("user_data/backtest_results/opt2_MomRegime15mLb21_is.zip")
B_val = eq_series("user_data/backtest_results/opt2_MomRegime15mLb21_val.zip")
# splice: chain VAL's 2023 %-returns onto IS equity (2021-22 kept from IS verbatim)
B = B_is.copy()
r23 = B_val.pct_change().fillna(B_val.iloc[0] / INIT - 1)
prev = B.loc[B.index < pd.Timestamp("2023-01-01", tz="UTC")].iloc[-1]
for d in r23.index[r23.index >= pd.Timestamp("2023-01-01", tz="UTC")]:
    prev = prev * (1 + r23.loc[d])
    B.loc[d] = prev

def mom(x):
    r = x.pct_change().fillna(x.iloc[0] / INIT - 1)
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1

mA, mN, mB = mom(A), mom(N), mom(B)
mB_full = mom(pd.read_csv(os.path.join(RES, "returns_daily.csv"), index_col=0, parse_dates=True)
              .assign(eq=lambda x: 10000 * (1 + x["B"]).cumprod())["eq"])

df_leg = pd.DataFrame({"A": mA, "N": mN, "B_splice": mB})
df_new = pd.DataFrame({"A": mA, "N": mN, "B_rerun": mB_full})
print("== legacy splice (original IS+VAL data), monthly realized returns corr ==")
print(df_leg.corr().round(3).to_string())
print("\n== PRT full-window rerun B, monthly realized returns corr ==")
print(df_new.corr().round(3).to_string())
print("\nsplice vs rerun monthly corr of B:", round(df_leg['B_splice'].corr(df_new['B_rerun']), 3))
