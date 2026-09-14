"""PRT03: mark-to-market daily equity reconstruction from trades + 1h futures candles.

Method (per sleeve zip):
  - cash(t) = 10000 + sum(profit_abs of trades with close_date <= t)
    (profit_abs includes fees + funding exactly as freqtrade accounts them)
  - each open trade contributes
        seg_realized(t) + dir*units(t)*(price_1h(t)-avg_cost(t)) + lump(t)
    where seg_realized comes from average-cost accounting over the embedded
    `orders` array, and lump = profit_abs - gross_total (fees+funding) is
    accrued linearly over [open, close].  At the first hour >= close_date the
    contribution is handed over to cash (set to 0) so nothing is double counted.
  - hourly equity -> daily = last hour of the UTC day ((ts-1us).floor(D)).

Usage: python prt03_mtm.py <zipname> <tag> [out_csv]
"""
import json, os, sys, zipfile
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
DATA = os.path.join(ROOT, r"user_data\data\binance\futures")
START = pd.Timestamp("2021-01-01", tz="UTC")
END = pd.Timestamp("2024-01-01", tz="UTC")
INIT = 10000.0

_pair_px = {}


def pair_prices(pair):
    if pair not in _pair_px:
        base = pair.split("/")[0]
        f = os.path.join(DATA, f"{base}_USDT_USDT-1h-futures.feather")
        d = pd.read_feather(f)
        d["date"] = pd.to_datetime(d["date"], utc=True)
        _pair_px[pair] = d.set_index("date")["close"].sort_index()
    return _pair_px[pair]


def trade_path(t):
    """Hourly MTM contribution of one open trade, 0 after handover hour."""
    dirn = -1.0 if t["is_short"] else 1.0
    open_ts = pd.to_datetime(t["open_date"])
    close_ts = pd.to_datetime(t["close_date"])

    evs = []
    for o in t.get("orders", []):
        ts = pd.to_datetime(o["order_filled_timestamp"], unit="ms", utc=True)
        amt, px = float(o["amount"]), float(o["safe_price"])
        add = (o["ft_order_side"] == "buy") != bool(t["is_short"])
        evs.append((ts, amt if add else -amt, px))
    evs.sort(key=lambda x: x[0])

    # walk chronologically with (units, basis) average-cost accounting
    u, b = 0.0, 0.0
    states = []  # (from_ts, to_ts, units, avg, realized)
    rg = 0.0
    prev = open_ts
    for ts, d, px in evs:
        if ts != prev:
            states.append((prev, ts, u, (b / u if u > 1e-12 else 0.0), rg))
            prev = ts
        if d > 1e-12:
            b += d * px
            u += d
        elif d < -1e-12 and u > 1e-12:
            avg = b / u
            take = min(-d, u)
            rg += dirn * take * (px - avg)
            b -= take * avg
            u -= take
    states.append((prev, close_ts, u, (b / u if u > 1e-12 else 0.0), rg))

    gross_total = rg + dirn * u * (float(t["close_rate"]) - (b / u if u > 1e-12 else 0.0))
    lump = float(t["profit_abs"]) - gross_total  # fees + funding

    hold_ns = max((close_ts - open_ts).value, 1)
    # handover rule: cash steps in at the first hour >= close_ts; the path covers
    # strictly earlier hours only, so nothing is double-counted at the boundary
    hrs = pd.date_range(open_ts.floor("h"), close_ts, freq="1h", inclusive="left")
    if len(hrs) == 0:
        return None, lump
    px = pair_prices(t["pair"]).reindex(hrs, method="ffill")
    vals = np.zeros(len(hrs))
    si = 0
    for i, h in enumerate(hrs):
        while si < len(states) - 1 and states[si][1] <= h:
            si += 1
        a, b2, uu, aa, rr = states[si]
        un = dirn * uu * (px.iloc[i] - aa) if uu > 1e-12 else 0.0
        frac = min(max((h - open_ts).value / hold_ns, 0.0), 1.0)
        vals[i] = rr + un + lump * frac
    return pd.Series(vals, index=hrs), lump


def reconstruct(zname):
    if not os.path.isabs(zname):
        base = ROOT if "research_deepen" in zname \
            else os.path.join(ROOT, "user_data", "backtest_results")
        zname = os.path.join(base, zname)
    with zipfile.ZipFile(zname) as f:
        main = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n][0]
        d = json.loads(f.read(main))
    s = list(d["strategy"].values())[0]
    trades = s["trades"]

    cl = pd.DataFrame([(pd.to_datetime(t["close_date"]), float(t["profit_abs"])) for t in trades],
                      columns=["ts", "pnl"]).sort_values("ts")
    cash_steps = cl.groupby("ts")["pnl"].sum().cumsum() + INIT

    pieces, recon_err = [], []
    for t in trades:
        path, _ = trade_path(t)
        if path is None:
            continue
        # reconciliation check at last kept hour: value should be close to profit_abs
        recon_err.append(abs(path.iloc[-1] - float(t["profit_abs"])))
        pieces.append(path)

    idx = pd.date_range(START, END, freq="1h", inclusive="left")
    cash_h = cash_steps.reindex(idx.union(cash_steps.index)).ffill().reindex(idx)
    cash_h.iloc[0] = INIT
    cash_h = cash_h.ffill().fillna(INIT)
    unreal = pd.concat(pieces).groupby(level=0).sum().sort_index() if pieces else pd.Series(0.0, index=idx)
    un_h = unreal.reindex(idx.union(unreal.index)).fillna(0.0).groupby(level=0).sum().reindex(idx).fillna(0.0)
    eq_h = (cash_h + un_h).iloc[1:]
    day = (eq_h.index - pd.Timedelta(microseconds=1)).floor("D")
    deq = eq_h.groupby(day).last()
    deq = deq[(deq.index >= pd.Timestamp("2021-01-01", tz="UTC")) & (deq.index <= pd.Timestamp("2023-12-31", tz="UTC"))]
    return deq, dict(n_trades=len(trades),
                     recon_err_p95=round(float(np.percentile(recon_err, 95)), 2) if recon_err else None,
                     recon_err_max=round(max(recon_err), 2) if recon_err else None,
                     final_eq=round(float(deq.iloc[-1]), 1),
                     freqtrade_total=round(INIT + float(cl["pnl"].sum()), 1))


if __name__ == "__main__":
    zname, tag = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
        ROOT, "research_deepen", "portfolio", "results", f"mtm_daily_{tag}.csv")
    deq, diag = reconstruct(zname)
    deq.to_csv(out, header=[f"eq_{tag}"])
    print(tag, zname, "->", out)
    for k, v in diag.items():
        print(" ", k, v)
    print("  daily n:", len(deq), "range:", deq.index[0].date(), "->", deq.index[-1].date())
