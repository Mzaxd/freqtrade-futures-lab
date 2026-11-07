# BULL evaluation: official-protocol yearly/DD30 extraction from result zips.
import zipfile, json, sys
import pandas as pd

FROZEN = {
    "v1": ("backtest-result-2026-11-07_04-59-51.zip", "BullFastreHalf"),
    "v1f": ("backtest-result-2026-11-07_04-59-46.zip", "BullFastreFull"),
    "v2": ("backtest-result-2026-11-07_04-59-55.zip", "BullLadder"),
    "v3": ("backtest-result-2026-11-07_05-00-01.zip", "BullFastreHalfLadder"),
    "v4": ("backtest-result-2026-11-07_04-59-37.zip", "BullCoinFast"),
    "v5": ("backtest-result-2026-11-07_04-59-40.zip", "BullIntraday"),
    "frozen": ("backtest-result-2026-11-07_03-56-10.zip", "OPT2_MomRegime15mLb21"),
}

def evaluate(zpath, strat):
    z = zipfile.ZipFile(f"/Users/caihaohan/Code/freqtrade-futures-lab/user_data/backtest_results/{zpath}")
    j = json.loads(z.read([n for n in z.namelist() if n.endswith(".json") and "config" not in n and "market" not in n][0]))
    s = j["strategy"][strat]
    wf = [n for n in z.namelist() if n.endswith("_wallet.feather")][0]
    import io
    w = pd.read_feather(io.BytesIO(z.read(wf)))
    w["date"] = pd.to_datetime(w["date"], utc=True)
    eq = w.set_index("date")["total_quote"].resample("D").last().ffill()
    yearly = {}
    for y, g in eq.groupby(eq.index.year):
        yearly[y] = g.iloc[-1] / g.iloc[0] - 1
    dd30 = (eq / eq.rolling(30).max() - 1).min()
    # anchor end value
    anchor = 3000 + s["profit_total_abs"] if s["starting_balance"] == 3000 else s["final_balance"]
    trades = s["trades"]
    return {"final_feather": float(eq.iloc[-1]), "final_json": float(s["final_balance"]),
            "profit_abs": float(s["profit_total_abs"]), "yearly": yearly,
            "dd30": float(dd30), "ntrades": len(trades), "liq": s.get("total_trades"),
            "left_open": len(s.get("left_open_trades", [])), "eq": eq,
            "trades": trades}

if __name__ == "__main__":
    res = {}
    for tag, (zp, st) in FROZEN.items():
        r = evaluate(zp, st)
        res[tag] = r
        ys = " ".join(f"{y}:{v:+.1%}" for y, v in sorted(r["yearly"].items()))
        print(f"{tag:7s} {ys}  dd30={r['dd30']:+.1%}  final={r['final_feather']:.0f}/{r['final_json']:.0f} trades={r['ntrades']} leftopen={r['left_open']}")

    # trade-diff validation for V1/V1f vs frozen (IS window)
    import pandas as pd
    def tdf(trades):
        t = pd.DataFrame(trades)
        t["open_date"] = pd.to_datetime(t["open_date"], utc=True)
        t["close_date"] = pd.to_datetime(t["close_date"], utc=True)
        return t
    fz = tdf(res["frozen"]["trades"])
    fz = fz[fz["close_date"] <= "2024-01-01"]
    for tag in ["v1", "v1f"]:
        vt = tdf(res[tag]["trades"])
        a = set(zip(fz["pair"], fz["open_date"], fz["close_date"]))
        b = set(zip(vt["pair"], vt["open_date"], vt["close_date"]))
        print(f"\n{tag} trade-set delta vs frozen IS:")
        print("  only-frozen:", sorted((str(x[1].date()), x[0].split("/")[0]) for x in a - b)[:12])
        print("  only-{}: {}".format(tag, sorted((str(x[1].date()), x[0].split("/")[0]) for x in b - a)[:12]))
