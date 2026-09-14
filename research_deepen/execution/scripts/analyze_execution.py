# -*- coding: utf-8 -*-
"""
Execution-model analysis for EXE_OPT4 (research_deepen/execution).

Steps (all evaluation strictly < 2024-01-01, CHARTER red line):
  extract : pull per-trade records from the archived backtest zip -> trades csv
  entry   : passive-limit entry fill simulation vs next-1h-open market baseline
  stop    : stop-loss slippage via 1m extremes inside the exit hour
  liq     : liquidation proximity under 2x isolated leverage vs 1m extremes

Usage (repo root):
  .venv/Scripts/python.exe research_deepen/execution/scripts/analyze_execution.py \
      --step all --zip research_deepen/execution/results/exe_opt4_baseline.zip
"""
import argparse
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
SANDBOX = REPO / "research_deepen" / "execution"
RESULTS = SANDBOX / "results"
DATA = REPO / "user_data" / "data" / "binance" / "futures"
END = pd.Timestamp("2024-01-01", tz="UTC")  # charter holdout boundary (exclusive)

OFFSET_BPS = [1, 2, 3, 5, 8, 10]
FEE_TAKER = 5.0   # bps, backtest assumption (0.05% both sides)
FEE_MAKER = 2.0   # bps, Binance USDT-M VIP0 maker (sensitivity only)


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- data loading
_pair_cache: dict = {}

def pair_file(pair: str, tf: str) -> Path:
    sym = pair.replace("/USDT:USDT", "_USDT_USDT")
    return DATA / f"{sym}-{tf}-futures.feather"


def load_pair(pair: str, tf: str) -> pd.DataFrame | None:
    key = (pair, tf)
    if key in _pair_cache:
        return _pair_cache[key]
    f = pair_file(pair, tf)
    if not f.exists():
        _pair_cache[key] = None
        return None
    df = pd.read_feather(f)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df[df["date"] < END].set_index("date").sort_index()
    _pair_cache[key] = df
    return df


def m1_slice(df1m: pd.DataFrame, start: pd.Timestamp, hours: float):
    """1m bars with date in [start, start+hours)."""
    end = start + pd.Timedelta(hours=hours)
    return df1m.loc[(df1m.index >= start) & (df1m.index < end)]


def candle_at(df: pd.DataFrame, ts: pd.Timestamp):
    """Row whose candle-open == ts."""
    try:
        return df.loc[ts]
    except KeyError:
        return None


# ---------------------------------------------------------------- step: extract
def step_extract(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        jname = [n for n in z.namelist()
                 if n.endswith(".json") and "config" not in n and "market" not in n][0]
        data = json.loads(z.read(jname))
    strat = list(data["strategy"].keys())
    assert len(strat) == 1, f"expected 1 strategy in zip, got {strat}"
    s = data["strategy"][strat[0]]
    tr = pd.DataFrame(s["trades"])
    tr["open_date"] = pd.to_datetime(tr["open_date"], utc=True)
    tr["close_date"] = pd.to_datetime(tr["close_date"], utc=True)
    keep = ["pair", "open_date", "close_date", "open_rate", "close_rate",
            "is_short", "leverage", "amount", "stake_amount", "exit_reason",
            "stop_loss_abs", "initial_stop_loss_abs", "profit_ratio",
            "trade_duration", "is_open"]
    tr = tr[keep].sort_values(["open_date", "pair"]).reset_index(drop=True)
    tr.to_csv(RESULTS / "trades_exe_opt4.csv", index=False)
    summary = {
        "strategy": strat[0],
        "backtest_start": s["backtest_start"], "backtest_end": s["backtest_end"],
        "n_trades": int(len(tr)), "n_open": int(tr["is_open"].sum()),
        "exit_reasons": tr["exit_reason"].value_counts().to_dict(),
        "direction": {"long": int((~tr["is_short"]).sum()),
                      "short": int(tr["is_short"].sum())},
        "tot_profit_ratio_equity_pct": s.get("profit_total", None) * 100 if s.get("profit_total") is not None else None,
    }
    (RESULTS / "backtest_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    log(f"[extract] {len(tr)} trades; exits: {summary['exit_reasons']}")
    log(f"[extract] profit_total={s.get('profit_total')} sharpe={s.get('sharpe')}")
    return tr


# ---------------------------------------------------------------- step: entry
def step_entry(tr: pd.DataFrame) -> None:
    rows = []
    skipped = {"no_1m": 0, "no_signal_candle": 0, "no_baseline_open": 0}
    for t in tr.itertuples():
        df1h = load_pair(t.pair, "1h")
        df1m = load_pair(t.pair, "1m")
        if df1m is None:
            skipped["no_1m"] += 1
            continue
        sig_ts = t.open_date - pd.Timedelta(hours=1)
        sig = candle_at(df1h, sig_ts)
        base = candle_at(df1h, t.open_date)
        if sig is None:
            skipped["no_signal_candle"] += 1
            continue
        if base is None:
            skipped["no_baseline_open"] += 1
            continue
        P = float(sig["close"])
        B = float(t.open_rate)  # baseline fill = next 1h open (backtest semantics)
        base_open_check = abs(B - float(base["open"])) / B  # should be ~0
        bars = m1_slice(df1m, t.open_date, 1)
        d = -1.0 if t.is_short else 1.0
        base_cost = d * (B / P - 1.0) * 1e4  # bps vs decision price P (+=worse)

        # chase price: next 1h open; if that is >= END use last 1m close of hour
        chase = candle_at(df1h, t.open_date + pd.Timedelta(hours=1))
        if chase is not None:
            C = float(chase["open"])
        else:
            c_last = bars["close"].iloc[-1] if len(bars) else np.nan
            C = float(c_last)
        chase_cost = d * (C / P - 1.0) * 1e4

        for o in OFFSET_BPS:
            L = P * (1 - d * o / 1e4)
            if len(bars) == 0:
                filled, fill_bar = False, None
            elif t.is_short:
                hit = bars[bars["high"] > L]
                filled, fill_bar = len(hit) > 0, (hit.index[0] if len(hit) else None)
            else:
                hit = bars[bars["low"] < L]
                filled, fill_bar = len(hit) > 0, (hit.index[0] if len(hit) else None)
            instant = bool(filled and fill_bar == bars.index[0])
            sim_price = L if filled else C
            sim_cost = d * (sim_price / P - 1.0) * 1e4
            rows.append({
                "pair": t.pair, "open_date": t.open_date, "is_short": bool(t.is_short),
                "P": P, "B": B, "C": C, "offset_bps": o, "filled": bool(filled),
                "instant": instant, "n_1m_bars": int(len(bars)),
                "base_cost_bps": base_cost, "chase_cost_bps": chase_cost,
                "sim_cost_bps": sim_cost, "saving_bps": base_cost - sim_cost,
                "base_open_check": base_open_check,
                "exit_reason": t.exit_reason,
            })
    det = pd.DataFrame(rows)
    det.to_csv(RESULTS / "entry_sim_trades.csv", index=False)

    def agg(g: pd.DataFrame) -> pd.Series:
        fr = g["filled"].mean()
        net = g["saving_bps"]
        filled = g[g["filled"]]["saving_bps"]
        unf = g[~g["filled"]]["saving_bps"]
        rng = np.random.default_rng(7)
        vals = net.to_numpy()
        boots = [rng.choice(vals, len(vals), replace=True).mean() for _ in range(2000)] \
            if len(vals) else [np.nan]
        return pd.Series({
            "n": len(g), "fill_rate": fr,
            "instant_share_of_all": g["instant"].mean(),
            "net_saving_bps_mean": net.mean(),
            "net_saving_bps_ci95_lo": float(np.percentile(boots, 2.5)),
            "net_saving_bps_ci95_hi": float(np.percentile(boots, 97.5)),
            "saving_filled_mean": filled.mean() if len(filled) else np.nan,
            "saving_unfilled_mean": unf.mean() if len(unf) else np.nan,
            "base_cost_mean_bps": g["base_cost_bps"].mean(),
            "chase_cost_mean_bps": g["chase_cost_bps"].mean(),
            # fee sensitivity: maker fee on fills, taker on chase
            "net_saving_incl_fee_bps": net.mean() + (FEE_TAKER - FEE_MAKER) * fr,
        })

    out = det.groupby(["offset_bps", "is_short"]).apply(agg, include_groups=False).reset_index()
    out_all = det.groupby("offset_bps").apply(agg, include_groups=False).reset_index()
    out_all.insert(1, "is_short", "ALL")
    fin = pd.concat([out_all, out], ignore_index=True).sort_values(["offset_bps", "is_short"])
    fin.to_csv(RESULTS / "entry_sim_summary.csv", index=False)
    log(f"[entry] skipped trades: {skipped}; simulated: {det['pair'].nunique()} pairs, "
        f"{len(det)//len(OFFSET_BPS)} trades x {len(OFFSET_BPS)} offsets")
    print(fin.to_string(index=False))


# ---------------------------------------------------------------- step: stop
def step_stop(tr: pd.DataFrame) -> None:
    st = tr[tr["exit_reason"] == "stop_loss"].copy()
    rows = []
    skipped = {"no_1m": 0, "no_cross": 0, "bad_align": 0}
    for t in st.itertuples():
        df1h = load_pair(t.pair, "1h")
        df1m = load_pair(t.pair, "1m")
        if df1m is None:
            skipped["no_1m"] += 1
            continue
        # align: stoploss exits recorded at the candle where they triggered
        exit_ts = t.close_date
        bar = candle_at(df1h, exit_ts)
        if bar is None:
            skipped["bad_align"] += 1
            continue
        T = float(t.close_rate)  # backtest assumption: fill exactly at trigger
        stop_pct = ((t.open_rate - T) / t.open_rate if not t.is_short
                    else (T - t.open_rate) / t.open_rate)
        bars = m1_slice(df1m, exit_ts, 1)
        if len(bars) == 0:
            skipped["no_1m"] += 1
            continue
        if t.is_short:
            hit = bars[bars["high"] >= T]
        else:
            hit = bars[bars["low"] <= T]
        if len(hit) == 0:
            skipped["no_cross"] += 1
            continue
        tb = hit.iloc[0]
        if t.is_short:
            gap = bool(tb["open"] >= T)
            slip_close = (tb["close"] - T) / T * 1e4
            slip_ext = (tb["high"] - T) / T * 1e4
            hour_ext = (bars["high"].max() - T) / T * 1e4
        else:
            gap = bool(tb["open"] <= T)
            slip_close = (T - tb["close"]) / T * 1e4
            slip_ext = (T - tb["low"]) / T * 1e4
            hour_ext = (T - bars["low"].min()) / T * 1e4
        rows.append({
            "pair": t.pair, "close_date": exit_ts, "is_short": bool(t.is_short),
            "open_rate": t.open_rate, "trigger": T, "stop_pct": stop_pct,
            "slip_close_bps": slip_close, "slip_ext_bps": slip_ext,
            "slip_hour_ext_bps": hour_ext, "gap_open": gap,
            "is_catastrophe": bool(stop_pct > 0.10),  # -0.30 cap at 2x ~ 15% move
            "leverage": t.leverage,
        })
    det = pd.DataFrame(rows)
    det.to_csv(RESULTS / "stop_slippage_trades.csv", index=False)

    def q(g, col):
        return g[col].quantile([0.5, 0.95, 0.99]).round(2).to_dict() if len(g) else {}

    summary = []
    for name, g in [("ALL", det)] + [(f"short={k}", det[det["is_short"] == k])
                                     for k in (True, False)] + \
            [(f"cat={k}", det[det["is_catastrophe"] == k]) for k in (False, True)]:
        summary.append({
            "group": name, "n": len(g),
            "slip_close_p50/p95/p99_bps": q(g, "slip_close_bps"),
            "slip_ext_p50/p95/p99_bps": q(g, "slip_ext_bps"),
            "slip_hour_ext_p50/p95/p99_bps": q(g, "slip_hour_ext_bps"),
            "gap_open_share": float(g["gap_open"].mean()) if len(g) else None,
            "stop_pct_p50": float(g["stop_pct"].quantile(0.5)) if len(g) else None,
            "mean_slip_close_bps": float(g["slip_close_bps"].mean()) if len(g) else None,
            "mean_slip_ext_bps": float(g["slip_ext_bps"].mean()) if len(g) else None,
        })
    (RESULTS / "stop_slippage_summary.json").write_text(
        json.dumps({"skipped": skipped, "groups": summary}, indent=2, default=str))
    log(f"[stop] {len(det)} stoploss exits analysed; skipped: {skipped}")
    for s in summary:
        log(f"  {s['group']}: n={s['n']} close-est {s['slip_close_p50/p95/p99_bps']} "
            f"ext-est {s['slip_ext_p50/p95/p99_bps']} gap_share={s['gap_open_share']}")


# ---------------------------------------------------------------- step: liq
MMR = 0.01  # Binance USDT-M isolated tier-1 maintenance margin (conservative 1%)

def step_liq(tr: pd.DataFrame) -> None:
    lev = 2.0
    # isolated liq: margin exhausted minus maintenance requirement
    m_liq = (1.0 / lev - MMR) / (1.0 - MMR)  # adverse price move to liquidation
    # per-trade stop distance from entry: the EFFECTIVE stop is the tighter of
    # the custom ATR stop (stop_loss_abs) and the static catastrophe cap
    # (initial_stop_loss_abs = -0.30 at 2x = 15% price move) — both are live.
    st = tr.copy()
    st["atr_stop"] = st["stop_loss_abs"]
    st["cat_stop"] = st["initial_stop_loss_abs"]
    st["stop_pct_atr"] = np.where(st["is_short"],
                                  (st["atr_stop"] - st["open_rate"]) / st["open_rate"],
                                  (st["open_rate"] - st["atr_stop"]) / st["open_rate"])
    st["stop_pct_cat"] = np.where(st["is_short"],
                                  (st["cat_stop"] - st["open_rate"]) / st["open_rate"],
                                  (st["open_rate"] - st["cat_stop"]) / st["open_rate"])
    # effective = tighter (smaller distance); NaN-safe
    st["stop_pct"] = st[["stop_pct_atr", "stop_pct_cat"]].min(axis=1, skipna=True)
    st = st[st["stop_pct"].notna()].copy()
    st["gap_needed_pct"] = m_liq - st["stop_pct"]  # single-jump size that skips stop->liq

    # max 1m bar range per coin 2021-2023 + top extreme events universe-wide
    maxbar, all_rng = {}, []
    for pair in tr["pair"].unique():
        df1m = load_pair(pair, "1m")
        if df1m is None:
            continue
        rng = (df1m["high"] - df1m["low"]) / df1m["open"]
        maxbar[pair] = {"max_1m_range_pct": float(rng.max()) * 100,
                        "when": str(rng.idxmax()),
                        "n_bars_range_gt10pct": int((rng > 0.10).sum()),
                        "n_bars_range_gt20pct": int((rng > 0.20).sum())}
        top = rng.nlargest(10)
        for ts, v in top.items():
            all_rng.append({"pair": pair, "ts": str(ts), "range_pct": float(v) * 100})
    events = sorted(all_rng, key=lambda r: -r["range_pct"])[:15]
    # overlap: was a strategy trade open on that pair within +/- 60 min of the event?
    for ev in events:
        ts = pd.Timestamp(ev["ts"])
        mask = ((st["pair"] == ev["pair"]) &
                (st["open_date"] <= ts + pd.Timedelta(minutes=60)) &
                (st["close_date"] >= ts - pd.Timedelta(minutes=60)))
        ev["trade_open_nearby"] = bool(mask.any())
        if mask.any():
            row = st[mask].iloc[0]
            ev["nearby_trade_window"] = f"{row['open_date']} -> {row['close_date']}"

    # per-trade empirical breach check: max single-1m-bar range during holding window
    breaches = 0
    checked = 0
    for t in st.itertuples():
        df1m = load_pair(t.pair, "1m")
        if df1m is None:
            continue
        win = df1m.loc[(df1m.index >= t.open_date) & (df1m.index <= t.close_date)]
        if len(win) == 0:
            continue
        checked += 1
        if ((win["high"] - win["low"]) / win["open"]).max() > t.gap_needed_pct:
            breaches += 1
    out = {
        "leverage": lev, "mmr_assumed": MMR,
        "liq_move_pct": m_liq * 100,
        "stop_pct_distribution": {
            "p50": float(st["stop_pct"].quantile(0.5)) * 100,
            "p95": float(st["stop_pct"].quantile(0.95)) * 100,
            "max": float(st["stop_pct"].max()) * 100,
        },
        "gap_needed_pct_distribution": {
            "p50": float(st["gap_needed_pct"].quantile(0.5)) * 100,
            "min": float(st["gap_needed_pct"].min()) * 100,
        },
        "n_liquidation_exits_in_backtest": int((tr["exit_reason"] == "liquidation").sum()),
        "stop_pct_atr_distribution": {
            "p50": float(st["stop_pct_atr"].quantile(0.5)) * 100,
            "max": float(st["stop_pct_atr"].max()) * 100,
        },
        "effective_stop_pct_distribution": {
            "p50": float(st["stop_pct"].quantile(0.5)) * 100,
            "p95": float(st["stop_pct"].quantile(0.95)) * 100,
            "max": float(st["stop_pct"].max()) * 100,
        },
        "max_1m_bar_per_coin": maxbar,
        "max_1m_range_across_universe_pct": max(v["max_1m_range_pct"] for v in maxbar.values()),
        "top_extreme_1m_events": events,
        "trades_checked": checked,
        "trades_with_singlebar_breach_of_gap": breaches,
    }
    (RESULTS / "liq_proximity.json").write_text(json.dumps(out, indent=2, default=str))
    log(f"[liq] liq_move={out['liq_move_pct']:.2f}%  eff-stop p50={out['effective_stop_pct_distribution']['p50']:.2f}% "
        f"max={out['effective_stop_pct_distribution']['max']:.2f}%  max 1m range={out['max_1m_range_across_universe_pct']:.2f}%  "
        f"breaches={breaches}/{checked}  liquidation exits={out['n_liquidation_exits_in_backtest']}")
    for ev in events[:8]:
        log(f"  extreme: {ev['pair']} {ev['ts']} range={ev['range_pct']:.1f}% open_nearby={ev['trade_open_nearby']}")


# ---------------------------------------------------------------- step: stats
def step_stats(tr: pd.DataFrame) -> None:
    det = pd.read_csv(RESULTS / "entry_sim_trades.csv",
                      parse_dates=["open_date"])
    det["open_date"] = pd.to_datetime(det["open_date"], utc=True)
    o1 = det[det["offset_bps"] == 1].copy()
    o1["year"] = o1["open_date"].dt.year
    q = lambda s: {p: round(float(s.quantile(p / 100)), 2) for p in (5, 50, 95, 99)}
    out = {
        "alignment": {
            "max_abs_base_open_vs_1hopen_rel": float(det["base_open_check"].max()),
            "n_zero_check_gt_1e-4": int((det["base_open_check"] > 1e-4).sum()),
        },
        "base_cost_bps_ALL": {**q(o1["base_cost_bps"]),
                              "mean": float(o1["base_cost_bps"].mean()),
                              "mean_abs": float(o1["base_cost_bps"].abs().mean())},
        "chase_cost_bps_ALL": q(o1["chase_cost_bps"]),
        "net_saving_by_year_o1_bps": o1.groupby("year")["saving_bps"].mean().round(2).to_dict(),
        "net_saving_by_year_o1_fillrate": o1.groupby("year")["filled"].mean().round(3).to_dict(),
        "net_saving_by_year_o2_bps": det[det["offset_bps"] == 2].assign(
            year=pd.to_datetime(det.loc[det["offset_bps"] == 2, "open_date"]).dt.year
        ).groupby("year")["saving_bps"].mean().round(2).to_dict(),
    }
    # stop-loss drag in PnL terms
    ss = pd.read_csv(RESULTS / "stop_slippage_trades.csv", parse_dates=["close_date"])
    n_all = len(tr)
    drag = {
        "mean_slip_close_bps": float(ss["slip_close_bps"].mean()),
        "mean_slip_ext_bps": float(ss["slip_ext_bps"].mean()),
        "share_stoploss_trades": len(ss) / n_all,
        "per_trade_avg_drag_close_bps": float(ss["slip_close_bps"].mean()) * len(ss) / n_all,
        "per_trade_avg_drag_ext_bps": float(ss["slip_ext_bps"].mean()) * len(ss) / n_all,
        "per_trade_avg_drag_hourext_bps": float(ss["slip_hour_ext_bps"].mean()) * len(ss) / n_all,
        "stop_pct_distribution": q(ss["stop_pct"] * 100),
    }
    out["stop_drag"] = drag
    (RESULTS / "stats_extra.json").write_text(json.dumps(out, indent=2, default=str))
    log(f"[stats] base_cost ALL: {out['base_cost_bps_ALL']}")
    log(f"[stats] yearly net saving o=1bps: {out['net_saving_by_year_o1_bps']}")
    log(f"[stats] stop drag: {drag}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all",
                    choices=["all", "extract", "entry", "stop", "liq", "stats"])
    ap.add_argument("--zip", type=Path, default=None)
    args = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    tr = None
    if args.step in ("all", "extract"):
        assert args.zip and args.zip.exists(), "--zip required for extract"
        tr = step_extract(args.zip)
    if args.step in ("entry", "stop", "liq", "stats", "all") and tr is None:
        tr = pd.read_csv(RESULTS / "trades_exe_opt4.csv",
                         parse_dates=["open_date", "close_date"])
        tr["open_date"] = pd.to_datetime(tr["open_date"], utc=True)
        tr["close_date"] = pd.to_datetime(tr["close_date"], utc=True)
    if args.step in ("all", "entry"):
        step_entry(tr)
    if args.step in ("all", "stop"):
        step_stop(tr)
    if args.step in ("all", "liq"):
        step_liq(tr)
    if args.step in ("all", "stats"):
        step_stats(tr)


if __name__ == "__main__":
    main()
