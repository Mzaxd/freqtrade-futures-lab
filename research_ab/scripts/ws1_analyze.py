# WS1 analysis: stop-distance / notional / stake distributions for sleeves A (DP_OPT4)
# and B (DP_SleeveB) from existing 3-coin backtest zips (wallet base 10000 USDT).
# Read-only; results printed to stdout. See research_ab/ws1_min_capital.md.
import io
import json
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
ZIP_A = ROOT + r"\user_data\backtest_results\backtest-result-2026-11-03_08-22-30.zip"  # DP_OPT4 3p
ZIP_B = ROOT + r"\user_data\backtest_results\backtest-result-2026-11-03_08-24-51.zip"  # DP_SleeveB 3p
INIT = 10000.0


def load_zip(zname):
    zf = zipfile.ZipFile(zname)
    main = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n][0]
    d = json.loads(zf.read(main))
    s = list(d["strategy"].values())[0]
    wname = [n for n in zf.namelist() if n.endswith("wallet.feather")][0]
    w = pd.read_feather(io.BytesIO(zf.read(wname)))
    w = w[w["currency"] == "USDT"][["date", "total_quote"]].sort_values("date")
    w["date"] = pd.to_datetime(w["date"], utc=True)
    return s, w


def eq_at(w, ts):
    # equity (total wallet in USDT quote) at (or just before) timestamp ts
    idx = w["date"].searchsorted(pd.Timestamp(ts), side="right") - 1
    return float(w["total_quote"].iloc[idx])


def q(x, ps=(5, 25, 50, 75, 90, 95)):
    return {f"p{p}": round(float(np.percentile(x, p)), 6) for p in ps} | {
        "min": round(float(min(x)), 6), "max": round(float(max(x)), 6),
        "n": int(len(x)), "mean": round(float(np.mean(x)), 6)}


def analyze_a():
    s, w = load_zip(ZIP_A)
    rows = []
    for t in s["trades"]:
        sl = t.get("initial_stop_loss_abs")
        stop_pct = abs(t["open_rate"] - sl) / t["open_rate"] if sl else np.nan
        notional = t["amount"] * t["open_rate"]
        eq = eq_at(w, t["open_date"])
        rows.append(dict(
            pair=t["pair"], short=t["is_short"], open_date=t["open_date"],
            open_rate=t["open_rate"], stop_pct=stop_pct,
            leverage=t["leverage"], stake=t["stake_amount"], notional=notional,
            eq=eq, notional_frac=notional / eq, stake_frac=t["stake_amount"] / eq,
            theo_frac=0.01 / stop_pct if stop_pct and stop_pct > 0 else np.nan,
            exit=t["exit_reason"],
        ))
    df = pd.DataFrame(rows)
    print("=" * 80)
    print(f"SLEEVE A (DP_OPT4, {len(df)} trades, wallet {INIT:.0f} base)")
    print("=" * 80)
    print("\n-- stop_pct (|open_rate - initial_stop|/open_rate), by pair --")
    print(df.groupby("pair")["stop_pct"].apply(q).to_string())
    print("\n-- stop_pct overall --")
    print(q(df["stop_pct"].dropna().tolist()))
    floor_hits = (df["stop_pct"] <= 0.005 * 1.02).sum()
    print(f"stop_pct at/near floor 0.005 (<=0.51%): {floor_hits}/{len(df)}")
    print("\n-- notional as fraction of equity, by pair --")
    print(df.groupby("pair")["notional_frac"].apply(q).to_string())
    print("\n-- stake(margin) as fraction of equity, by pair --")
    print(df.groupby("pair")["stake_frac"].apply(q).to_string())
    cap_bound = (df["notional_frac"] > 0.699).sum()
    print(f"margin-cap-bound trades (notional_frac>0.699): {cap_bound}/{len(df)} "
          f"({cap_bound/len(df):.1%})")
    print("\n-- absolute notional USDT (base wallet 10000) --")
    print(df.groupby("pair")["notional"].apply(lambda x: q(x.tolist())).to_string())
    print("\n-- absolute stake USDT --")
    print(df.groupby("pair")["stake"].apply(lambda x: q(x.tolist())).to_string())
    # consistency: notional_frac vs 0.01/stop_pct capped at 0.70
    pred = np.minimum(df["theo_frac"], 0.70)
    err = (df["notional_frac"] - pred).abs()
    print(f"\nnotional_frac vs min(0.01/stop_pct, 0.70): median|err|={err.median():.5f}, "
          f"p95={err.quantile(.95):.5f}")
    # stop distance vs stop_atr_mult=2: stop_pct/2 = ATR/close
    # concurrency: worst simultaneous margin
    ev = []
    for _, r in df.iterrows():
        ev.append((r["open_date"], 1, r["stake_frac"]))
    close_map = {t["open_date"]: t["close_date"] for t in s["trades"]}
    cl = pd.DataFrame([(pd.Timestamp(t["close_date"]), t["pair"]) for t in s["trades"]],
                      columns=["ts", "pair"])
    ev = pd.DataFrame(ev, columns=["ts", "delta", "sf"])
    # build per-trade intervals and evaluate hourly overlap
    tr = df.copy()
    tr["open_ts"] = pd.to_datetime(tr["open_date"])
    tr["close_ts"] = [pd.Timestamp(close_map[o]) for o in tr["open_date"]]
    grid = pd.date_range(tr["open_ts"].min(), tr["close_ts"].max(), freq="1h")
    conc = np.zeros(len(grid))
    for _, r in tr.iterrows():
        m = (grid >= r["open_ts"]) & (grid < r["close_ts"])
        conc[m] += r["stake_frac"]
    i = int(np.argmax(conc))
    print(f"\nmax concurrent margin (sum stake_frac): {conc.max():.3f} at {grid[i]}  "
          f"-> x1.28 = {conc.max()*1.28:.3f}, x1.56 = {conc.max()*1.56:.3f}")
    for k in [1.0, 1.28, 1.56]:
        over = (conc * k > 1.0).mean()
        print(f"  recycle {k}: hours with margin>100% of A-wallet: {over:.4%}, "
              f"hours >70%: {(conc*k > 0.7).mean():.4%}")
    # entry price ranges per pair (for step-granularity math)
    print("\n-- open_rate range by pair --")
    print(df.groupby("pair")["open_rate"].apply(lambda x: q(x.tolist(), (5, 50, 95))).to_string())
    print("\n-- BTC amount (BTC) distribution --")
    btc = df[df["pair"] == "BTC/USDT:USDT"]
    print(q(btc["notional"].div(btc["open_rate"]).tolist()))
    # trade duration / holding
    print("\n-- trade duration days --")
    dur = (tr["close_ts"] - tr["open_ts"]).dt.total_seconds() / 86400
    print(q(dur.tolist()))
    # fees & funding in this backtest
    print("\n-- fee rates used --")
    print("fee_open sample:", s["trades"][0]["fee_open"], "fee_close:", s["trades"][0]["fee_close"])
    ff = [t["funding_fees"] for t in s["trades"]]
    print(f"funding_fees sum: {sum(ff):.1f} USDT over {len(ff)} trades")
    return df


def analyze_b():
    s, w = load_zip(ZIP_B)
    print("=" * 80)
    print(f"SLEEVE B (DP_SleeveB, {len(s['trades'])} trades, wallet {INIT:.0f} base)")
    print("=" * 80)
    sub = []  # per entry-order records (position_adjustment sub-orders included)
    for t in s["trades"]:
        eq0 = eq_at(w, t["open_date"])
        for j, o in enumerate(t["orders"]):
            if not o.get("ft_is_entry"):
                continue
            sub.append(dict(
                pair=t["pair"], j=j, ts=pd.Timestamp(
                    pd.to_datetime(o["order_filled_timestamp"], unit="ms", utc=True)),
                cost=float(o["cost"]), amount=float(o["amount"]),
                price=float(o["safe_price"]), eq0=eq0, lev=t["leverage"],
                first=(j == 0),
            ))
    bs = pd.DataFrame(sub)
    bs["eq_at"] = [eq_at(w, ts) for ts in bs["ts"]]
    bs["frac_eq"] = bs["cost"] / bs["eq_at"]
    print(f"\nentry sub-orders total: {len(bs)} (trades {len(s['trades'])}), "
          f"adds (j>0): {(~bs['first']).sum()}")
    print("\n-- per-sub-order notional (cost, USDT, base 10000) --")
    print(q(bs["cost"].tolist()))
    print("\n-- per-sub-order notional fraction of equity --")
    print(q(bs["frac_eq"].tolist()))
    print("\n-- INITIAL order only: notional fraction of equity --")
    print(q(bs[bs["first"]]["frac_eq"].tolist()))
    print("\n-- ADD orders only: notional fraction of equity --")
    addf = bs[~bs["first"]]
    if len(addf):
        print(q(addf["frac_eq"].tolist()))
        print("min add abs USDT:", round(addf["cost"].min(), 2),
              "p5:", round(addf["cost"].quantile(0.05), 2),
              "p25:", round(addf["cost"].quantile(0.25), 2))
    print("\n-- per-sub-order notional fraction, by pair --")
    print(bs.groupby("pair")["frac_eq"].apply(lambda x: q(x.tolist())).to_string())
    print("\n-- leverage used by B --")
    print(bs["lev"].unique())
    # trade-level: total notional built per trade (sum entry costs) / equity
    tr_rows = []
    for t in s["trades"]:
        entry_cost = sum(o["cost"] for o in t["orders"] if o.get("ft_is_entry"))
        eq0 = eq_at(w, t["open_date"])
        dur = (pd.Timestamp(t["close_date"]) - pd.Timestamp(t["open_date"])).total_seconds() / 86400
        tr_rows.append(dict(pair=t["pair"], cost=entry_cost, eq0=eq0,
                            frac=entry_cost / eq0, dur=dur,
                            funding=t["funding_fees"], profit=t["profit_abs"]))
    tb = pd.DataFrame(tr_rows)
    print("\n-- per-TRADE aggregated entry notional fraction of equity --")
    print(q(tb["frac"].tolist()))
    print("\n-- trade duration days --")
    print(q(tb["dur"].tolist()))
    print(f"trades with duration >= 18d: {(tb['dur'] >= 18).sum()}/{len(tb)}; "
          f"median dur {tb['dur'].median():.1f}d")
    print("\n-- funding share: sum funding_fees / sum entry notional --")
    print(f"total funding: {tb['funding'].sum():.1f} USDT; total entry notional: "
          f"{tb['cost'].sum():.0f} USDT; total profit_abs: {tb['profit'].sum():.0f}")
    # worst concurrent basket margin (sum of stake_frac hourly) — B margin = notional/lev
    print("\n-- B wallet equity trajectory (min/median/max) --")
    print(q(w["total_quote"].tolist(), (5, 50, 95)))
    # funding as pct of position notional annualized check: avg funding per trade / cost
    tb["fund_pct_cost"] = tb["funding"] / tb["cost"]
    print("\n-- per-trade funding_fees / trade entry notional --")
    print(q(tb["fund_pct_cost"].tolist()))
    return bs, tb


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    dfa = analyze_a()
    print()
    bs, tb = analyze_b()
    # persist raw per-trade/per-order tables for the C-level matrix step
    dfa.to_csv(ROOT + r"\research_ab\results\ws1_a_trades_dist.csv", index=False)
    bs.to_csv(ROOT + r"\research_ab\results\ws1_b_orders_dist.csv", index=False)
    tb.to_csv(ROOT + r"\research_ab\results\ws1_b_trades_dist.csv", index=False)
    print("\nsaved: research_ab/results/ws1_{a_trades,b_orders,b_trades}_dist.csv")
