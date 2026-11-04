# ws3 follow-up: clean signal classification (strip equity compounding drift) and
# the single unmatched trade in d.
import json
import zipfile

import pandas as pd

RES = r"D:\Code\AIQuant\freqtrade-futures-lab\research_ab\results"
DATA = r"D:\Code\AIQuant\freqtrade-futures-lab\user_data\data\binance\futures\BTC_USDT_USDT-1d-futures.feather"


def load(tag):
    with zipfile.ZipFile(rf"{RES}\ws3_{tag}.zip") as f:
        main = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n and "meta" not in n][0]
        d = json.loads(f.read(main))
    tr = pd.DataFrame(list(d["strategy"].values())[0]["trades"])
    for col in ("open_date", "close_date"):
        tr[col] = pd.to_datetime(tr[col], utc=True)
    return tr.sort_values("open_date").reset_index(drop=True)


a = load("a_OPT9_base_3p")
c = load("c_OPT9_Recycle_128_3p")
d = load("d_OPT9_Recycle_156_3p")

dfe = pd.read_feather(DATA)
dfe["date"] = pd.to_datetime(dfe["date"], utc=True)
Pd = dfe.set_index("date")["close"].sort_index()
known = Pd.shift(1)
ron = (known > known.rolling(100).mean()).fillna(False)
recycle_day = ~ron

def realized_eq(df):
    cl = df[["close_date", "profit_abs"]].sort_values("close_date")
    return cl.set_index("close_date")["profit_abs"].cumsum() + 10000.0

def eq_at(path, t):
    s = path[path.index <= t]
    return float(s.iloc[-1]) if len(s) else 10000.0

ea, ec, ed = realized_eq(a), realized_eq(c), realized_eq(d)

def audit(overlay, eo, mult, name):
    m = a.merge(overlay, on=["pair", "open_date", "is_short"], suffixes=("_a", "_x"))
    m = m.sort_values("open_date").reset_index(drop=True)
    m["eq_a"] = [eq_at(ea, t) for t in m["open_date"]]
    m["eq_x"] = [eq_at(eo, t) for t in m["open_date"]]
    # implied multiplier strips compounding: (stake/eq) ratio
    m["implied"] = (m["stake_amount_x"] / m["eq_x"]) / (m["stake_amount_a"] / m["eq_a"])
    m["off"] = m["open_date"].dt.floor("D").map(lambda x: bool(recycle_day.loc[x]))
    post = m[m["open_date"] >= pd.Timestamp("2021-04-02", tz="UTC")]
    on_day = post[~post["off"]]
    off_day = post[post["off"]]
    print(f"--- {name} (MULT={mult}) post-warmup matched: {len(post)}")
    for label, g in (("ON days", on_day), ("OFF days", off_day)):
        imp = g["implied"]
        near1 = ((imp > 0.98) & (imp < 1.02)).mean()
        nearM = ((imp > mult - 0.02) & (imp < mult + 0.03)).mean()
        print(f"  {label}: n={len(g)}  implied~1: {near1:.3f}  implied~{mult}: {nearM:.3f}  "
              f"med={imp.median():.4f} min={imp.min():.4f} max={imp.max():.4f}")
    odd = post[~((post["implied"] > 0.98) & (post["implied"] < 1.02))
               & ~((post["implied"] > mult - 0.05) & (post["implied"] < mult + 0.05))]
    print(f"  trades NOT within +-2% of 1 or +-3-5% of {mult}: {len(odd)}")
    if len(odd):
        print(odd[["pair", "open_date", "implied", "stake_amount_a", "stake_amount_x", "off"]].to_string())
    # clean amplified share on OFF days
    print(f"  OFF-day trades with implied~{mult}: "
          f"{((off_day['implied'] > mult - 0.05) & (off_day['implied'] < mult + 0.05)).mean():.4f} "
          f"-> amplified trade share among post-warmup = {len(off_day) / len(post):.4f}")
    return m

mc = audit(c, ec, 1.28, "c 1.28")
md = audit(d, ed, 1.56, "d 1.56")

# ---- the unmatched trade in d ----
print("\n--- unmatched trade d vs a ---")
ka = set(map(tuple, a[["pair", "open_date", "is_short"]].values))
kd = set(map(tuple, d[["pair", "open_date", "is_short"]].values))
only_a = ka - kd
only_d = kd - ka
print("in a but not d:", only_a)
print("in d but not a:", only_d)
for p, t, s in list(only_a) + list(only_d):
    near_a = a[(a["pair"] == p) & ((a["open_date"] - t).abs() < pd.Timedelta(days=10))]
    near_d = d[(d["pair"] == p) & ((d["open_date"] - t).abs() < pd.Timedelta(days=10))]
    print(f"\ncontext around {p} {t} (is_short={s}):")
    print("a:", near_a[["pair", "open_date", "close_date", "is_short", "exit_reason", "stake_amount", "profit_abs"]].to_string())
    print("d:", near_d[["pair", "open_date", "close_date", "is_short", "exit_reason", "stake_amount", "profit_abs"]].to_string())
# all trades open at that time in both (MOT contention?)
for p, t, s in list(only_a) + list(only_d):
    print("\nopen positions in a at t:", a[(a["open_date"] < t) & (a["close_date"] > t)][["pair", "open_date", "close_date", "stake_amount"]].to_string())
    print("open positions in d at t:", d[(d["open_date"] < t) & (d["close_date"] > t)][["pair", "open_date", "close_date", "stake_amount"]].to_string())
