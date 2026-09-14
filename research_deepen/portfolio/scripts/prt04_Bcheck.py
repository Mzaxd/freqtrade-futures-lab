"""PRT04: reconcile PRT full-window B run vs frozen reference IS (21-22) + VAL (23).

Compares trade lists (pair, open_date, direction) and yearly PnL/equity.
"""
import json, os, zipfile
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"


def load(zdir, zname):
    with zipfile.ZipFile(os.path.join(ROOT, zdir, zname)) as f:
        m = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n][0]
        d = json.loads(f.read(m))
    s = list(d["strategy"].values())[0]
    tr = pd.DataFrame([{k: t[k] for k in ("pair", "open_date", "close_date", "is_short",
                                          "profit_abs", "profit_ratio")} for t in s["trades"]])
    tr["open_date"] = pd.to_datetime(tr["open_date"])
    tr["close_date"] = pd.to_datetime(tr["close_date"])
    return tr, s


full, sf = load(r"research_deepen\portfolio\results", "prt_B_momregime15mlb21_full.zip")
isr, sis = load(r"user_data\backtest_results", "opt2_MomRegime15mLb21_is.zip")
val, sva = load(r"user_data\backtest_results", "opt2_MomRegime15mLb21_val.zip")

print("== yearly realized PnL (profit_abs, USDT) ==")
for tag, tr in (("full", full), ("is_ref", isr), ("val_ref", val)):
    tr = tr.copy()
    tr["year"] = tr["close_date"].dt.year
    print(tag, tr.groupby("year")["profit_abs"].agg(["sum", "count"]).round(0).to_dict("index"))

# trade matching on (pair, open_date, direction) within 2021-2022 for full vs IS
k = lambda df, until: set(zip(df[df.open_date < until]["pair"],
                              df[df.open_date < until]["open_date"].astype(str),
                              df[df.open_date < until]["is_short"]))
f21 = k(full, "2023-01-01")
i21 = k(isr, "2030-01-01")
print("\nfull-run trades opened 21-22:", len(f21), " IS-ref trades:", len(i21),
      " matched:", len(f21 & i21), " full_only:", len(f21 - i21), " is_only:", len(i21 - f21))

# matched-trade PnL comparison
idx = pd.MultiIndex.from_tuples(f21 & i21)
fu = full[full.set_index(["pair", "open_date", "is_short"]).index.isin(f21)]
ir = isr[isr.set_index(["pair", "open_date", "is_short"]).index.isin(f21)]
mg = fu.merge(ir, on=["pair", "open_date", "is_short"], suffixes=("_f", "_i"))
mg["diff"] = mg["profit_abs_f"] - mg["profit_abs_i"]
print("matched n:", len(mg), " pnl diff: mean", round(mg["diff"].mean(), 1),
      "p50", round(mg["diff"].median(), 1), "p95abs", round(mg["diff"].abs().quantile(0.95), 1),
      " max", round(mg["diff"].abs().max(), 1))

# 2023 trades: full vs VAL
f23 = full[full.open_date >= "2023-01-01"]
print("\nfull 2023 trades:", len(f23), "pnl", round(f23["profit_abs"].sum(), 0))
print("val 2023 trades:", len(val), "pnl", round(val["profit_abs"].sum(), 0))
kv = set(zip(val["pair"], val["open_date"].astype(str), val["is_short"]))
kf = set(zip(f23["pair"], f23["open_date"].astype(str), f23["is_short"]))
print("matched:", len(kv & kf), "full_only:", len(kf - kv), "val_only:", len(kv - kf))
mv = f23[f23.set_index(["pair", "open_date", "is_short"]).index.isin(kv)]
mr = val[val.set_index(["pair", "open_date", "is_short"]).index.isin(kv)]
m23 = mv.merge(mr, on=["pair", "open_date", "is_short"], suffixes=("_f", "_v"))
m23["diff"] = m23["profit_abs_f"] - m23["profit_abs_v"]
print("2023 matched n:", len(m23), "pnl diff mean", round(m23["diff"].mean(), 1),
      "sum_f", round(m23["profit_abs_f"].sum(), 0), "sum_v", round(m23["profit_abs_v"].sum(), 0))
print("\nfull-only 2023 trades (first 10):")
print(f23[~f23.set_index(["pair", "open_date", "is_short"]).index.isin(kv)][
    ["pair", "open_date", "close_date", "profit_abs"]].head(10).to_string())
