# ws3 trade-level comparison: b vs a (regression identity), c/d vs a (sizing overlay).
import json
import sys
import zipfile

import numpy as np
import pandas as pd

RES = r"D:\Code\AIQuant\freqtrade-futures-lab\research_ab\results"
DATA = r"D:\Code\AIQuant\freqtrade-futures-lab\user_data\data\binance\futures\BTC_USDT_USDT-1d-futures.feather"


def load(tag):
    with zipfile.ZipFile(rf"{RES}\ws3_{tag}.zip") as f:
        main = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n and "meta" not in n][0]
        d = json.loads(f.read(main))
    s = list(d["strategy"].values())[0]
    tr = pd.DataFrame(s["trades"])
    for c in ("open_date", "close_date"):
        tr[c] = pd.to_datetime(tr[c], utc=True)
    return tr, s["total_trades"], s["profit_total"] if "profit_total" in s else None


a, _, _ = load("a_OPT9_base_3p")
b, _, _ = load("b_OPT9_Recycle_M10_3p")
c, _, _ = load("c_OPT9_Recycle_128_3p")
d, _, _ = load("d_OPT9_Recycle_156_3p")

# ---------------------------------------------------------------- regression b vs a
print("=" * 78)
print("REGRESSION b (MULT=1.0) vs a (OPT9 base)")
cols = [c for c in a.columns if c not in ()]
diff_cols = []
for col in cols:
    try:
        eq = (a[col].astype(str).values == b[col].astype(str).values).all()
    except Exception:
        eq = None
    if eq is False:
        diff_cols.append(col)
print(f"trades: a={len(a)} b={len(b)}; differing columns: {diff_cols if diff_cols else 'NONE — trade-identical'}")

# B recycle calendar from feather (same as regime_stats)
dfe = pd.read_feather(DATA)
dfe["date"] = pd.to_datetime(dfe["date"], utc=True)
Pd = dfe.set_index("date")["close"].sort_index()
known = Pd.shift(1)
ron = (known > known.rolling(100).mean()).fillna(False)   # risk_on during day D = ron[D]
recycle_day = ~ron


def day_of(ts):
    return ts.floor("D")


def compare(overlay, mult, name):
    print("=" * 78)
    print(f"OVERLAY {name} (MULT={mult}) vs a")
    m = a.merge(overlay, on=["pair", "open_date", "is_short"], suffixes=("_a", "_x"))
    print(f"matched on (pair,open_date,is_short): {len(m)}/{len(a)}")
    # exact order alignment as merged by open sequence
    m = m.sort_values("open_date").reset_index(drop=True)
    same_exit = (m["close_date_a"] == m["close_date_x"]).mean()
    same_exit_reason = (m["exit_reason_a"] == m["exit_reason_x"]).mean()
    same_rate = (m["close_rate_a"].round(6) == m["close_rate_x"].round(6)).mean()
    print(f"identical close_date: {same_exit:.4f}  exit_reason: {same_exit_reason:.4f}  close_rate: {same_rate:.4f}")
    if same_exit < 1.0:
        bad = m[m["close_date_a"] != m["close_date_x"]]
        print(f"  !! {len(bad)} trades with different close_date:")
        print(bad[["pair", "open_date", "close_date_a", "close_date_x",
                   "exit_reason_a", "exit_reason_x", "profit_abs_a", "profit_abs_x"]].to_string())
    # stake ratio classification
    m["ratio"] = m["stake_amount_x"] / m["stake_amount_a"]
    m["on_recycle_day"] = m["open_date"].dt.floor("D").map(lambda x: bool(recycle_day.loc[x]) if x in recycle_day.index else None)
    warm = m["open_date"] < pd.Timestamp("2021-04-02", tz="UTC")   # in-frame SMA100 warmup
    post = m[~warm].copy()
    amp = post["ratio"] > 1.001
    print(f"\ntrades in warmup (no signal, ratio forced ~1): {int(warm.sum())}, "
          f"mean ratio {m[warm]['ratio'].mean():.6f}")
    print(f"post-warmup trades: {len(post)}; amplified (ratio>1.001): {int(amp.sum())} "
          f"({amp.mean():.3f})")
    # OFF-day share among post-warmup ENTRY days
    ent_days = post["open_date"].dt.floor("D")
    off_share_days = post["on_recycle_day"].mean()
    print(f"OFF-day share among post-warmup entries: {off_share_days:.3f} "
          f"(calendar OFF share 2021-04-02..2026-09-12: "
          f"{recycle_day.loc['2021-04-02':'2026-09-12'].mean():.3f})")
    # signal-consistency audit: amplified <=> OFF day
    mis_amp = post[(amp != post["on_recycle_day"])]
    print(f"amplified-vs-OFF-day mismatches: {len(mis_amp)}")
    if len(mis_amp):
        print(mis_amp[["pair", "open_date", "ratio", "on_recycle_day"]].head(20).to_string())
    # ratio distribution of amplified trades (eq drift makes it ~= mult)
    r = post[amp]["ratio"]
    print(f"amplified ratio: min {r.min():.4f} p5 {r.quantile(.05):.4f} med {r.median():.4f} "
          f"p95 {r.quantile(.95):.4f} max {r.max():.4f}")
    # truncation audit: reconstruct equity (realized) + margin in use at each entry
    eq = {}
    for tag, df in (("a", a), ("x", overlay)):
        df = df.sort_values("open_date")
        # realized equity path at each entry: 10000 + sum(profit_abs of trades closed before open)
        closes = df[["close_date", "profit_abs"]].sort_values("close_date")
        eq_path = closes.set_index("close_date")["profit_abs"].cumsum() + 10000.0
        av = []
        for _, row in df.iterrows():
            real = eq_path[eq_path.index <= row["open_date"]]
            realized = real.iloc[-1] if len(real) else 10000.0
            # margin in use = stake of trades open at this instant
            inuse = df[(df["open_date"] < row["open_date"]) & (df["close_date"] > row["open_date"])]["stake_amount"].sum()
            av.append((realized, inuse))
        eq[tag] = av
    post_idx = post.index.values
    rows = []
    for i in post_idx:
        ra = a.sort_values("open_date").reset_index(drop=True)
        row_a = ra.loc[i]
        realized_a, inuse_a = eq["a"][i]
        realized_x, inuse_x = eq["x"][i]
        stake_a = row_a["stake_amount"]
        stake_x = overlay.sort_values("open_date").reset_index(drop=True).loc[i, "stake_amount"]
        margin_cap_a = 0.35 * realized_a
        parent_capped = stake_a >= margin_cap_a * 0.995
        # amplified-run caps: max_stake ~ realized*0.99 - inuse ; margin cap applies BEFORE mult
        max_stake_x = realized_x * 0.99 - inuse_x
        truncated_by_ms = amp.loc[i] and (stake_x >= max_stake_x * 0.995)
        rows.append(dict(i=i, date=row_a["open_date"], pair=row_a["pair"],
                         stake_a=stake_a, stake_x=stake_x,
                         parent_margin_capped=bool(parent_capped),
                         trunc_maxstake=bool(truncated_by_ms)))
    T = pd.DataFrame(rows)
    ampT = T[T["stake_x"] > T["stake_a"] * 1.001]
    print(f"\namplified trades in overlay: {len(ampT)}")
    print(f"  parent (OPT8) stake already at 0.35*equity margin cap in a: "
          f"{int(T['parent_margin_capped'].sum())} of {len(T)} post-warmup trades")
    print(f"  among amplified: parent-capped {int(ampT['parent_margin_capped'].sum())}, "
          f"max_stake-truncated (approx) {int(ampT['trunc_maxstake'].sum())}")
    print(f"  non-amplified but parent-capped: "
          f"{int(T[(T['stake_x'] <= T['stake_a'] * 1.001) & T['parent_margin_capped']].sum().iloc[0] if len(T[(T['stake_x'] <= T['stake_a'] * 1.001) & T['parent_margin_capped']]) else 0)}")
    # PnL attribution
    pnl_a, pnl_x = a["profit_abs"].sum(), overlay["profit_abs"].sum()
    print(f"\ntotal profit_abs: a={pnl_a:.1f} overlay={pnl_x:.1f} "
          f"delta={pnl_x - pnl_a:+.1f} ({(pnl_x - pnl_a) / pnl_a * 100:+.1f}%)")
    # profit on amplified vs non-amplified trades
    mm = post.copy()
    mm["pnl_x"] = overlay.sort_values("open_date").reset_index(drop=True).loc[post_idx, "profit_abs"].values
    mm["pnl_a"] = a.sort_values("open_date").reset_index(drop=True).loc[post_idx, "profit_abs"].values
    mm["amp"] = amp.values
    print(f"  pnl on amplified trades: a={mm[mm['amp']]['pnl_a'].sum():.0f} -> x={mm[mm['amp']]['pnl_x'].sum():.0f}")
    print(f"  pnl on non-amplified trades: a={mm[~mm['amp']]['pnl_a'].sum():.0f} -> x={mm[~mm['amp']]['pnl_x'].sum():.0f}")
    return m, T


mc, Tc = compare(c, 1.28, "c 1.28")
md, Td = compare(d, 1.56, "d 1.56")

# ---------------------------------------------------------------- flip-day entry audit
print("=" * 78)
print("flip-day audit: does sleeve A open positions on regime-flip days?")
flips = recycle_day.loc["2021-01-01":"2026-09-12"]
flip_days = flips.index[flips != flips.shift(1)]
ent_days_a = a["open_date"].dt.floor("D")
iso_off = [d for d in flip_days if (flips.loc[d] != flips.shift(-1).loc[d] if d + pd.Timedelta(days=1) in flips.index else False)]
n_flip_with_entry = sum(1 for fd in flip_days if (ent_days_a == fd).any())
print(f"flip days: {len(flip_days)}; with A entries same day: {n_flip_with_entry}")
seg = (flips != flips.shift(1)).cumsum()
short_off = [g.index[0] for _, g in flips.groupby(seg) if (~g).all() and len(g) <= 3]
n_short_with_entry = sum(1 for fd in short_off if (ent_days_a == fd).any())
print(f"isolated OFF segments (<=3d): {len(short_off)}; with A entries same day: {n_short_with_entry}")
# semantic note: multiplier flip mid-position does nothing to open trades — verify stake of
# trades OPENED pre-flip is identical in a vs c (they are matched trades; sizes only set at entry)
print("(open positions are never resized: stake fixed at entry; flip only affects NEW entries)")
