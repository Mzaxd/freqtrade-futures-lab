"""WS-C2 event-driven 5m grid simulator for research_chop (2026-11-04).

Quantifies how much a neutral dual-sided grid earns (and how much inventory risk
it takes) inside gated chop windows, per PRE_REGISTRATION.md section 5.

Gating
  Gate signal = g2/g4 columns of research_chop/data/regime_1h_{SYM}.csv
  (t-hour label uses only data closed at/before t -> effective from t+1h).
  Alignment: label row t is shifted to effective time t+1h, then merge_asof
  (backward) onto 5m bars. A 5m bar at time T therefore consumes the gate from
  the hourly candle that closed at floor_hour(T) -- strictly causal.
  Gate OFF -> inventory market-cleared at the close of the first OFF 5m bar
  (taker fee): this realises the gate-lag cost.

Grid (PRE_REG section 5)
  On gate open: anchor = close of the last completed 5m bar; levels at
  anchor*(1 +/- i*step), i=1..L; step = 1h ATR%(14) at the gate-opening label
  row * k.  Neutral dual grid (primary): buy limits below anchor, sell-to-open
  limits above; after each fill a closing order rests one spacing away on the
  other side (buy fill p -> sell-close at p+spacing; short-open fill p ->
  buy-close at p-spacing); when a close fills the opening order at that level
  re-arms (oscillation harvesting).  Long-only grid (sensitivity): buys below
  anchor only, no shorts.

Fill assumption (conservative, core)
  cross (primary): buy fills only if a later 5m bar's LOW is STRICTLY below the
  limit; sell fills only if HIGH is STRICTLY above.  Fill price = limit price.
  touch (sensitivity): <= / >= instead (optimistic bound).  Same bar fills each
  resting order at most once.  Intrabar path: up candle assumed open->low->high
  ->close (buys then sells), down candle open->high->low->close (sells then
  buys).  ALL fills charged taker 0.0005 (maker rebates ignored: conservative).

Inventory & risk
  Net-exposure cap: |net_qty * price| <= 2x current equity, checked at every
  fill; a fill that would breach it is skipped (order stays resting).
  Funding: actual 8h funding_rate feather charged on net inventory
  (positive rate: longs pay / shorts receive), applied at each funding
  timestamp to the position held entering it, priced at the previous 5m close.
  Approximate liquidation: if net-inventory unrealized PnL <= -98% of current
  equity (cash + unrealized) at any 5m close, force-close everything at that
  close (taker) and terminate the episode (PRE_REG: "window realises all
  losses").  Disclosed approximation: no maintenance-margin tiers.
  Price beyond grid outer edge while gate ON: inventory kept, ALL orders
  suspended (active only on bars whose open is inside [lower,upper] edge) until
  price returns or gate closes.  No re-anchor inside an episode (disclosed).

Windows (PRE_REG section 3)
  IS = 2021-01-01 .. 2024-01-01 (exclusive end, freqtrade timerange convention)
  OS = 2024-01-01 .. 2026-09-12 (exclusive end).  Episodes straddling a window
  boundary are cut and cleared at that boundary (disclosed artifact).

CLI
  python grid_sim.py one --pair BTC --gate g2 --L 12 --k 0.5 --mode dual --fill cross --period IS
  python grid_sim.py batch IS                       # full 8-config design grid
  python grid_sim.py batch OS --gate g2 --L 20 --k 1.0   # selected cfg + sensitivities
Outputs: research_chop/logs/grid_episodes_{period}.csv and
         research_chop/logs/grid_summary_{period}.csv (appended per run).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FDATA = ROOT / "user_data" / "data" / "binance" / "futures"
RDATA = ROOT / "research_chop" / "data"
LOGS = ROOT / "research_chop" / "logs"

TAKER = 0.0005
INIT_EQ = 10_000.0
LEV_CAP = 2.0            # net notional <= 2x equity, fill-time check
LIQ_FRAC = 0.98          # force-close when float loss >= 98% of current equity
MIN_LEVEL_FRAC = 0.01    # drop grid levels priced below 1% of anchor
PAIRS = ("BTC", "ETH", "SOL")
WINDOWS = {
    "IS": (pd.Timestamp("2021-01-01"), pd.Timestamp("2024-01-01")),
    "OS": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-09-12")),
}
IS_GRID = [  # pre-registered IS design grid (L x k x gate), dual grid + cross fills
    {"gate": g, "L": L, "k": k, "mode": "dual", "fill": "cross"}
    for g in ("g2", "g4") for L in (12, 20) for k in (0.5, 1.0)
]

_CACHE: dict[str, dict] = {}


# --------------------------------------------------------------------------- data


def _naive(s: pd.Series) -> np.ndarray:
    if getattr(s.dtype, "tz", None) is not None:
        s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return s.to_numpy()


def load_pair(sym: str) -> dict:
    """Load 5m ohlc + causal gate/atr on 5m + funding events. Cached per pair."""
    if sym in _CACHE:
        return _CACHE[sym]
    f5 = FDATA / f"{sym}_USDT_USDT-5m-futures.feather"
    df5 = pd.read_feather(f5).sort_values("date").reset_index(drop=True)
    out = {
        "date": _naive(df5["date"]),
        "open": df5["open"].to_numpy(float),
        "high": df5["high"].to_numpy(float),
        "low": df5["low"].to_numpy(float),
        "close": df5["close"].to_numpy(float),
    }
    # 1h ATR%(14) exactly as scripts/regime_label.py build_features
    h1 = pd.read_feather(FDATA / f"{sym}_USDT_USDT-1h-futures.feather")
    pc = h1["close"].shift(1)
    tr = pd.concat(
        [h1["high"] - h1["low"], (h1["high"] - pc).abs(), (h1["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    atr = pd.DataFrame(
        {"date": _naive(h1["date"]), "atr_pct": (tr.rolling(14).mean() / h1["close"]).to_numpy(float)}
    )
    reg = pd.read_csv(RDATA / f"regime_1h_{sym}.csv")
    reg_date = _naive(pd.to_datetime(reg["date"], utc=True))
    base = pd.DataFrame({"date": reg_date, "g2": reg["g2"].astype(bool), "g4": reg["g4"].astype(bool)})
    eff = base.merge(atr, on="date", how="left")          # atr of the SAME label row
    eff["date"] = eff["date"] + np.timedelta64(1, "h")     # effective from t+1h
    eff = eff.sort_values("date")
    eff["date"] = eff["date"].astype("datetime64[ns]")
    left = pd.DataFrame({"date": out["date"].astype("datetime64[ns]")})
    m = pd.merge_asof(left, eff, on="date", direction="backward")
    out["g2"] = m["g2"].fillna(False).to_numpy(bool)
    out["g4"] = m["g4"].fillna(False).to_numpy(bool)
    out["atr"] = m["atr_pct"].to_numpy(float)
    fr = pd.read_feather(FDATA / f"{sym}_USDT_USDT-1h-funding_rate.feather").sort_values("date")
    out["fr_date"] = _naive(fr["date"]).astype("datetime64[ns]")
    out["fr_rate"] = fr["funding_rate"].to_numpy(float)
    _CACHE[sym] = out
    return out


def find_episodes(on: np.ndarray) -> list[tuple[int, int]]:
    idx = np.where(on)[0]
    if len(idx) == 0:
        return []
    splits = np.where(np.diff(idx) > 1)[0]
    starts = np.r_[idx[0], idx[splits + 1]]
    ends = np.r_[idx[splits], idx[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


# ------------------------------------------------------------------------ engine


def simulate_episode(
    p: dict, i0: int, i1: int, eq0: float, gate: str, L: int, k: float,
    mode: str, fill: str, i_max: int,
) -> dict:
    """Run one gate-ON episode [i0..i1] (global 5m indices). Returns episode row."""
    d = p["date"]; o = p["open"]; h = p["high"]; l = p["low"]; c = p["close"]
    row = dict(
        t_start=str(d[i0]), t_end=str(d[min(i1 + 1, len(d) - 1)]),
        bars_on=i1 - i0 + 1, end_reason="gate_off", skipped=False,
        n_fills=0, n_rt=0, n_liq=0, n_cap_skip=0, n_oor_bars=0,
        grid_profit=0.0, fees=0.0, funding=0.0, clear_pnl=0.0,
        max_float_loss=0.0, max_net_expo=0.0, start_equity=eq0, end_equity=eq0,
    )
    atr = p["atr"][i0]  # atr% of the label row that switched the gate on (causal)
    if eq0 <= 0 or not np.isfinite(atr) or atr <= 0:
        row["skipped"] = True
        row["end_reason"] = "no_atr_or_insolvent"
        return row
    dual = mode == "dual"
    touch = fill == "touch"
    anchor = c[i0 - 1]
    step = atr * k
    spacing = anchor * step
    pb = anchor * (1.0 - step * np.arange(1, L + 1))          # buy-open levels
    ps = anchor * (1.0 + step * np.arange(1, L + 1))          # short-open levels
    valid = pb > MIN_LEVEL_FRAC * anchor                      # deep-crash guard
    Lb = int(valid.sum())
    if Lb == 0:
        row["skipped"] = True
        row["end_reason"] = "levels_below_guard"
        return row
    qty = LEV_CAP * eq0 / (Lb * anchor)                       # fixed qty per level
    lower_edge, upper_edge = pb[valid].min(), ps[-1]

    cash = eq0
    net_qty = 0.0        # + long, - short (units)
    net_cost = 0.0       # sum( +/- qty * entry )
    lhold = np.zeros(L, bool)   # below-side: True = holding (close rests), False = armed
    shold = np.zeros(L, bool)   # above-side (dual only)
    lentry = np.zeros(L); sentry = np.zeros(L)
    fr_ptr = int(np.searchsorted(p["fr_date"], d[i0 - 1], side="right"))
    fr_d, fr_r = p["fr_date"], p["fr_rate"]

    def unrealized(px: float) -> float:
        return px * net_qty - net_cost

    def exposure_ok(dq: float, px: float) -> bool:
        eq = cash + unrealized(px)
        return abs((net_qty + dq) * px) <= LEV_CAP * max(eq, 0.0)

    i = i0
    while i <= i1:
        # funding events in (d[i-1], d[i]] on position held entering them
        while fr_ptr < len(fr_d) and fr_d[fr_ptr] <= d[i]:
            if fr_d[fr_ptr] > d[i - 1] and net_qty != 0.0:
                pay = net_qty * c[i - 1] * fr_r[fr_ptr]  # +rate: longs pay
                cash -= pay
                row["funding"] -= pay
            fr_ptr += 1
        oi, hi, li, ci = o[i], h[i], l[i], c[i]
        if lower_edge <= oi <= upper_edge:  # orders suspended outside grid range
            buys, sells = [], []
            for j in range(L):
                if not valid[j]:
                    continue
                if not lhold[j]:
                    buys.append((pb[j], "lo", j))
                else:
                    sells.append((pb[j] + spacing, "lc", j))
                if dual:
                    if shold[j]:
                        buys.append((ps[j] - spacing, "sc", j))
                    else:
                        sells.append((ps[j], "so", j))

            def do_buys() -> None:
                nonlocal cash, net_qty, net_cost, row
                for px, kind, j in sorted(buys, key=lambda x: -x[0]):  # path falls
                    hit = (li <= px) if touch else (li < px)
                    if not hit or not exposure_ok(+qty, px):
                        if hit and not exposure_ok(+qty, px):
                            row["n_cap_skip"] += 1
                        continue
                    fee = TAKER * qty * px
                    cash -= fee
                    row["fees"] += fee
                    if kind == "lo":
                        net_qty += qty; net_cost += qty * px
                        lentry[j] = px; lhold[j] = True
                    else:  # sc: close short
                        pnl = qty * (sentry[j] - px)
                        cash += pnl
                        row["grid_profit"] += pnl; row["n_rt"] += 1
                        net_qty += qty; net_cost += qty * sentry[j]
                        shold[j] = False
                    row["n_fills"] += 1

            def do_sells() -> None:
                nonlocal cash, net_qty, net_cost, row
                for px, kind, j in sorted(sells, key=lambda x: x[0]):  # path rises
                    hit = (hi >= px) if touch else (hi > px)
                    if not hit or not exposure_ok(-qty, px):
                        if hit and not exposure_ok(-qty, px):
                            row["n_cap_skip"] += 1
                        continue
                    fee = TAKER * qty * px
                    cash -= fee
                    row["fees"] += fee
                    if kind == "so":
                        net_qty -= qty; net_cost -= qty * px
                        sentry[j] = px; shold[j] = True
                    else:  # lc: close long
                        pnl = qty * (px - lentry[j])
                        cash += pnl
                        row["grid_profit"] += pnl; row["n_rt"] += 1
                        net_qty -= qty; net_cost -= qty * lentry[j]
                        lhold[j] = False
                    row["n_fills"] += 1

            if ci >= oi:      # up bar: open->low->high->close
                do_buys(); do_sells()
            else:             # down bar: open->high->low->close
                do_sells(); do_buys()
        else:
            row["n_oor_bars"] += 1

        row["max_net_expo"] = max(row["max_net_expo"], abs(net_qty * ci))
        unrl = unrealized(ci)
        row["max_float_loss"] = min(row["max_float_loss"], unrl)
        eq = cash + unrl
        if eq <= 0.0 or unrl <= -LIQ_FRAC * max(eq, 0.0):
            fee = TAKER * abs(net_qty) * ci
            cash += unrl - fee
            row["fees"] += fee
            row["clear_pnl"] += unrl
            net_qty = 0.0; net_cost = 0.0
            row["n_liq"] += 1
            row["end_reason"] = "liquidation"
            row["t_end"] = str(d[i])
            row["end_equity"] = cash
            return row
        i += 1

    # gate OFF (or window boundary): market-clear at close of the first OFF bar;
    # an episode that reaches the window edge is cleared at that edge bar
    j = i1 + 1 if i1 + 1 <= i_max else i1
    row["t_end"] = str(d[j])
    if j == i1:
        row["end_reason"] = "window_end"
    unrl = unrealized(c[j])
    if net_qty != 0.0:
        fee = TAKER * abs(net_qty) * c[j]
        cash += unrl - fee
        row["fees"] += fee
        row["clear_pnl"] += unrl
        net_qty = 0.0; net_cost = 0.0
    row["end_equity"] = cash
    return row


def run_config(sym: str, gate: str, L: int, k: float, mode: str, fill: str, period: str):
    p = load_pair(sym)
    w0, w1 = WINDOWS[period]
    d = p["date"]
    lo = int(np.searchsorted(d, np.datetime64(w0)))
    hi = int(np.searchsorted(d, np.datetime64(w1), side="right")) - 1
    eps = find_episodes(p[gate][lo : hi + 1])
    eps = [(a + lo, b + lo) for a, b in eps]
    eq, rows = INIT_EQ, []
    for i0, i1 in eps:
        r = simulate_episode(p, i0, i1, eq, gate, L, k, mode, fill, hi)
        ident = eq + r["grid_profit"] + r["clear_pnl"] - r["fees"] + r["funding"]
        assert abs(r["end_equity"] - ident) < 1e-6 * max(1.0, abs(ident)), "equity identity broken"
        r.update(pair=sym, gate=gate, L=L, k=k, mode=mode, fill=fill, period=period)
        rows.append(r)
        eq = r["end_equity"]
    tot = dict(
        pair=sym, gate=gate, L=L, k=k, mode=mode, fill=fill, period=period,
        n_ep=len(rows), net_profit=eq - INIT_EQ, ret_pct=(eq / INIT_EQ - 1.0) * 100.0,
        grid_profit=sum(r["grid_profit"] for r in rows), fees=sum(r["fees"] for r in rows),
        funding=sum(r["funding"] for r in rows), clear_pnl=sum(r["clear_pnl"] for r in rows),
        n_liq=sum(r["n_liq"] for r in rows), n_rt=sum(r["n_rt"] for r in rows),
        n_fills=sum(r["n_fills"] for r in rows),
        max_float_loss=min([r["max_float_loss"] for r in rows], default=0.0),
        n_pass=sum(
            1 for r in rows
            if r["n_fills"] == 0 or (-r["max_float_loss"]) < r["grid_profit"]
        ),
        n_skipped=sum(1 for r in rows if r["skipped"]),
    )
    return rows, tot


# ------------------------------------------------------------------------ batch


def pool(summary: pd.DataFrame, keys=("gate", "L", "k", "mode", "fill")) -> pd.DataFrame:
    g = summary.groupby(list(keys)).agg(
        net_profit=("net_profit", "sum"),
        grid_profit=("grid_profit", "sum"),
        fees=("fees", "sum"),
        funding=("funding", "sum"),
        clear_pnl=("clear_pnl", "sum"),
        n_ep=("n_ep", "sum"),
        n_pass=("n_pass", "sum"),
        n_liq=("n_liq", "sum"),
        n_rt=("n_rt", "sum"),
        max_float_loss=("max_float_loss", "min"),
        n_skipped=("n_skipped", "sum"),
    ).reset_index()
    g["pass_frac"] = g["n_pass"] / g["n_ep"].clip(lower=1)
    return g.sort_values("net_profit", ascending=False)


def append_csv(df: pd.DataFrame, path: Path) -> None:
    header = not path.exists()
    df.to_csv(path, mode="a", header=header, index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=["one", "batch"])
    ap.add_argument("period", choices=["IS", "OS"])
    ap.add_argument("--pair", choices=PAIRS)
    ap.add_argument("--gate", choices=["g2", "g4"])
    ap.add_argument("--L", type=int)
    ap.add_argument("--k", type=float)
    ap.add_argument("--mode", choices=["dual", "long"], default="dual")
    ap.add_argument("--fill", choices=["cross", "touch"], default="cross")
    a = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if a.what == "one":
        for req in ("pair", "gate", "L", "k"):
            if getattr(a, req) is None:
                ap.error(f"--{req} required for 'one'")
        rows, tot = run_config(a.pair, a.gate, a.L, a.k, a.mode, a.fill, a.period)
        ep = pd.DataFrame(rows)
        append_csv(ep, LOGS / f"grid_episodes_{a.period}.csv")
        append_csv(pd.DataFrame([tot]), LOGS / f"grid_summary_{a.period}.csv")
        print(pd.DataFrame([tot]).to_string(index=False))
        print(ep.head(30).to_string(index=False))
        return

    if a.period == "IS" and a.gate is None:
        cfgs = IS_GRID
    else:
        if a.gate is None or a.L is None or a.k is None:
            ap.error("batch OS (or IS sensitivity) needs --gate --L --k of the selected cfg")
        base = dict(gate=a.gate, L=a.L, k=a.k)
        cfgs = [
            {**base, "mode": "dual", "fill": "cross"},   # primary
            {**base, "mode": "dual", "fill": "touch"},   # fill-assumption sensitivity
            {**base, "mode": "long", "fill": "cross"},   # long-only sensitivity
            {**base, "mode": "long", "fill": "touch"},
        ]
    all_rows, summaries = [], []
    for cfg in cfgs:
        for sym in PAIRS:
            rows, tot = run_config(sym, cfg["gate"], cfg["L"], cfg["k"],
                                   cfg["mode"], cfg["fill"], a.period)
            all_rows.extend(rows)
            summaries.append(tot)
            print(f"[{time.time()-t0:7.1f}s] {sym} {cfg} net={tot['net_profit']:+.0f} "
                  f"grid={tot['grid_profit']:+.0f} fees={tot['fees']:.0f} "
                  f"fund={tot['funding']:+.0f} clear={tot['clear_pnl']:+.0f} "
                  f"nep={tot['n_ep']} pass={tot['n_pass']} liq={tot['n_liq']}")
    ep = pd.DataFrame(all_rows)
    sm = pd.DataFrame(summaries)
    append_csv(ep, LOGS / f"grid_episodes_{a.period}.csv")
    append_csv(sm, LOGS / f"grid_summary_{a.period}.csv")
    pooled = pool(sm)
    pooled.to_csv(LOGS / f"grid_pooled_{a.period}.csv", index=False)
    print(f"\n== pooled ({a.period}) ==\n{pooled.to_string(index=False)}")


if __name__ == "__main__":
    main()
