"""uni/step4 — build point-in-time monthly universe snapshots (pre-registered).

Rule (research_improve/uni/pre_reg.md §1; constants FROZEN — do not edit):
  month M membership, from daily bars STRICTLY BEFORE M:
    age >= 60d since first daily bar
    median(daily notional, last 30 bars) >= 10,000,000 USDT
    std(log ret, last 30 bars) * sqrt(365)  >= 0.60

Tradable set (data-availability constraint, disclosed): frozen 12 +
ACTIVE 2022+ listings with lifetime median daily notional >= 10M
(candidate_pairs.txt) + RAYSOL. Snapshot CSVs cover ONLY these;
admissions among the other ~440 daily-covered symbols are counted as the
coverage-gap diagnostic.
"""
import json
import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DAILY = os.path.join(HERE, "daily")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

AGE_MIN, LIQ_MIN, RV_MIN = 60, 10_000_000.0, 0.60
FROZEN12 = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
            "LINK", "DOT", "LTC", "UNI"]
MONTHS = pd.period_range("2021-02", "2026-11", freq="M")


def load_series() -> dict[str, pd.DataFrame]:
    out = {}
    for fn in os.listdir(DAILY):
        if not fn.endswith(".csv"):
            continue
        sym = fn[:-4]
        df = pd.read_csv(os.path.join(DAILY, fn))
        if len(df) < 10:
            continue
        idx = pd.to_datetime(df["date"].astype("int64"), unit="ms", utc=True)
        s = pd.DataFrame({"qv": df["quote_volume"].astype(float).values,
                          "close": df["close"].astype(float).values},
                         index=idx).sort_index()
        out[sym] = s[~s.index.duplicated()]
    for c in FROZEN12:
        fe = (f"{ROOT}/user_data/data/binance/futures/"
              f"{c}_USDT_USDT-1d-futures.feather")
        df = pd.read_feather(fe)[["date", "close", "volume"]]
        idx = pd.DatetimeIndex(df["date"])
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        s = pd.DataFrame({"qv": (df["volume"] * df["close"]).astype(float).values,
                          "close": df["close"].astype(float).values}, index=idx)
        s = s.sort_index()
        out[c + "USDT"] = s[~s.index.duplicated()]
    return out


def admit(s: pd.DataFrame, m0: pd.Timestamp):
    h = s[s.index < m0]
    if len(h) < 30:
        return False, {}
    age = (m0 - h.index[0]).days
    l30 = h.iloc[-30:]
    liq = float(l30["qv"].median())
    r = np.log(l30["close"] / l30["close"].shift(1)).dropna()
    rv = float(r.std() * math.sqrt(365)) if len(r) >= 15 else float("nan")
    ok = age >= AGE_MIN and liq >= LIQ_MIN and (rv == rv and rv >= RV_MIN)
    return ok, {"age": age, "liq30": liq, "rv30": rv}


def main():
    series = load_series()
    tradable = {c + "USDT" for c in FROZEN12}
    for line in open(os.path.join(HERE, "candidate_pairs.txt")):
        p = line.strip()
        if p:
            tradable.add(p.split("/")[0] + "USDT")
    tradable.add("RAYSOLUSDT")

    ext_rows, pit_rows, summary, diag_rows = [], [], [], []
    delisted_diag = ["TONUSDT", "FTMUSDT", "WAVESUSDT", "LUNAUSDT", "TOMOUSDT",
                     "AKROUSDT", "FRONTUSDT", "PHBUSDT", "MBLUSDT"]
    for month in MONTHS:
        m0 = month.to_timestamp(how="start").tz_localize("UTC")
        n_all = n_trad = n_new = 0
        gap_syms = []
        for sym, s in series.items():
            if sym == "RAYUSDT":       # rename alias, zero volume
                continue
            ok, d = admit(s, m0)
            if sym in delisted_diag:
                d = dict(d)
                d.update({"month": str(month), "symbol": sym, "admitted": ok})
                diag_rows.append(d)
            if not ok:
                continue
            n_all += 1
            pair = sym[:-4] + "/USDT:USDT"
            if sym in tradable:
                n_trad += 1
                pit_rows.append({"pair": pair, "month": str(month)})
                if sym[:-4] not in FROZEN12:
                    ext_rows.append({"pair": pair, "month": str(month)})
                    n_new += 1
            else:
                gap_syms.append(sym)
        summary.append({"month": str(month), "n_rule_all": n_all,
                        "n_tradable": n_trad, "n_new_tradable": n_new,
                        "gap": len(gap_syms), "gap_syms": ",".join(gap_syms)})

    pd.DataFrame(ext_rows).to_csv(os.path.join(HERE, "universe_ext.csv"), index=False)
    pd.DataFrame(pit_rows).to_csv(os.path.join(HERE, "universe_pit.csv"), index=False)
    pd.DataFrame(summary).to_csv(os.path.join(HERE, "snapshot_summary.csv"), index=False)
    pd.DataFrame(diag_rows).to_csv(os.path.join(HERE, "delisted_rule_diag.csv"), index=False)

    su = pd.DataFrame(summary)
    print("tradable symbols:", len(tradable))
    print(su.groupby(su.month.str[:4])[["n_rule_all", "n_tradable",
                                        "n_new_tradable", "gap"]].mean().round(1))
    new_ext = pd.DataFrame(ext_rows)
    if len(new_ext):
        per = new_ext.groupby("pair")["month"].nunique().sort_values(ascending=False)
        print("\nnew-coin admitted months (top 20):")
        print(per.head(20).to_string())
        print("distinct new coins ever admitted:", per.shape[0])


if __name__ == "__main__":
    main()
