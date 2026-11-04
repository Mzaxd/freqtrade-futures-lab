# c1_combine.py — WS-C1 OS adjudication (PRE_REG §4 C1 acceptance):
#   1) AB+C vs AB on the OS window (2024-01-01..2026-09-12): daily fixed-weight
#      return concatenation (ws2_analysis.py method). AB = 0.7*A3 + 0.3*B3
#      (A3 is the OPT4-based reference curve — caliber difference disclosed in
#      the report; the live A is OPT9_Recycle@1.21/ARL_2x). AB+C cedes wC from
#      A/B proportionally: rP = (1-wC)*rAB + wC*rC, wC in {0.05,0.10,0.15}.
#   2) Acceptance A: OS Sharpe(AB+C) >= OS Sharpe(AB).
#      Acceptance B: chop-window slope improvement >= +3pp. Chop day set:
#      day t is a chop day iff on day t-1 at least one of BTC/ETH/SOL had
#      g2 or g4 ON for >=1 hour (hourly labels shifted one day for causality).
#      Slope = mean daily portfolio return on chop days (also shown
#      annualized x365.25; the +3pp criterion is judged on the annualized
#      figure, interpretation disclosed).
#   3) C standalone trade economics (IS + OS zips) incl. fee share and the
#      "edge < 2x round-trip fee" flag (PRE_REG §6.3).
# Run: .venv/Scripts/python.exe research_chop/scripts/c1_combine.py
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ANN = 365.25
OS_START, OS_END = "2024-01-01", "2026-09-13"   # OS return days 01-02..09-12
WC_GRID = [0.05, 0.10, 0.15]


def sharpe(r: pd.Series) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(ANN)) if sd > 0 else float("nan")


def load_eq(path: Path, col: str) -> pd.Series:
    s = pd.read_csv(path, index_col=0, parse_dates=True)[col]
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    return s.sort_index()


def chop_days_os() -> pd.DataFrame:
    frames = []
    for p in ("BTC", "ETH", "SOL"):
        d = pd.read_csv(ROOT / f"research_chop/data/regime_1h_{p}.csv",
                        parse_dates=["date"])
        d["on"] = d["g2"] | d["g4"]
        g = d.set_index("date")["on"].resample("D").max().fillna(False)
        frames.append(g.rename(p))
    m = pd.concat(frames, axis=1)
    m.index = m.index.tz_localize(None)         # align with naive MTM day stamps
    any_on = m.any(axis=1)                      # union across 3 pairs
    btc_on = m["BTC"]
    # shift(1): day t decision uses day t-1 gate state (causal)
    out = pd.DataFrame({"any3": any_on, "btc": btc_on}).shift(1)
    return out.astype(bool)


def econ(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as f:
        main = [n for n in f.namelist() if n.endswith(".json")
                and "_config" not in n and "_market_change" not in n][0]
        s = list(json.loads(f.read(main))["strategy"].values())[0]
    t = pd.DataFrame(s["trades"])
    notional = t["stake_amount"] * t["leverage"]
    fees = notional * (t["fee_open"] + t["fee_close"])
    net_bps = (t["profit_abs"] / notional) * 1e4
    fund = t["funding_fees"].abs().sum()
    gross_win = t.loc[t["profit_abs"] > 0, "profit_abs"].sum()
    return {
        "trades": len(t),
        "win%": 100.0 * (t["profit_abs"] > 0).mean(),
        "avg_net_usdt": t["profit_abs"].mean(),
        "avg_net_bps_notional": net_bps.mean(),
        "rt_fee_bps": 2 * 5.0,   # 5bp per side -> 10bp round trip on notional
        "fees_usdt": fees.sum(),
        "funding_usdt": fund,
        "fee+fnd/grosswin": (fees.sum() + fund) / gross_win if gross_win > 0 else np.nan,
        "profit_total%": 100 * s["profit_total"],
        "sharpe_ft": s["sharpe"],
        "calmar_ft": s["calmar"],
        "maxdd%": 100 * s["max_drawdown_account"],
        "avg_lev_notional": notional.mean(),
        "edge_thin": bool(net_bps.mean() < 2 * 10.0),  # <2x round-trip fee (10bp)
    }


def main() -> None:
    a = load_eq(ROOT / "user_data/logs/mtm_daily_A3.csv", "eq_A3")
    b = load_eq(ROOT / "user_data/logs/mtm_daily_B3.csv", "eq_B3")
    c = load_eq(ROOT / "research_chop/logs/mtm_daily_C1os.csv", "eq_C1OS")
    c_g4 = load_eq(ROOT / "research_chop/logs/mtm_daily_C1osg4.csv", "eq_C1OSG4")

    rA, rB = a.pct_change().dropna(), b.pct_change().dropna()
    rC_full = c.pct_change().dropna()
    os_idx = rA.index[(rA.index >= pd.Timestamp(OS_START))
                      & (rA.index < pd.Timestamp(OS_END))]
    common = os_idx.intersection(rB.index).intersection(rC_full.index)
    rA, rB, rC = rA.loc[common], rB.loc[common], rC_full.loc[common]
    rCg4 = c_g4.pct_change().dropna().reindex(common).fillna(0.0)
    rAB = 0.7 * rA + 0.3 * rB

    cd = chop_days_os().reindex(common).fillna(False)
    chop_any, chop_btc = cd["any3"], cd["btc"]

    def block(name: str, r: pd.Series) -> dict:
        eq = (1 + r).cumprod()
        span = (common[-1] - common[0]).days
        return {
            "config": name,
            "total%": 100 * (eq.iloc[-1] - 1),
            "ann%": 100 * (eq.iloc[-1] ** (ANN / span) - 1),
            "sharpe": sharpe(r),
            "maxdd%": 100 * (eq / eq.cummax() - 1).min(),
            "chop_slope_bp/d": 1e4 * r[chop_any].mean(),
            "chop_slope_ann%": 100 * r[chop_any].mean() * ANN,
            "nonchop_ann%": 100 * r[~chop_any].mean() * ANN,
        }

    rows = [block("AB (0.7A3+0.3B3)", rAB), block("C alone (g2_96_25)", rC),
            block("C alone (g4_96_25, xchk)", rCg4)]
    for w in WC_GRID:
        rows.append(block(f"AB+C wC={w:.2f}", (1 - w) * rAB + w * rC))
    for w in WC_GRID:
        rows.append(block(f"AB+Cg4 wC={w:.2f} (xchk)", (1 - w) * rAB + w * rCg4))
    tbl = pd.DataFrame(rows)
    print("=== OS window %s .. %s  (%d return days; chop days any3=%d, btc=%d) ==="
          % (common[0].date(), common[-1].date(), len(common),
             chop_any.sum(), chop_btc.sum()))
    print(tbl.round(3).to_string(index=False))

    print("\n--- Acceptance A: OS Sharpe(AB+C) >= OS Sharpe(AB)?  [AB Sharpe = %.3f]"
          % sharpe(rAB))
    for w in WC_GRID:
        sh = sharpe((1 - w) * rAB + w * rC)
        print(f"  wC={w:.2f}: Sharpe={sh:.3f} -> {'PASS' if sh >= sharpe(rAB) else 'FAIL'}")
    base_slope = rAB[chop_any].mean()
    print("\n--- Acceptance B: chop-window slope improvement >= +3pp (annualized)")
    print(f"  AB chop slope: {1e4*base_slope:.2f} bp/day = {100*base_slope*ANN:+.2f}% ann")
    for w in WC_GRID:
        r = (1 - w) * rAB + w * rC
        sl = r[chop_any].mean()
        dpp = 100 * (sl - base_slope) * ANN
        print(f"  wC={w:.2f}: slope {1e4*sl:.2f} bp/d ({100*sl*ANN:+.2f}% ann) "
              f"improvement {dpp:+.2f}pp -> {'PASS' if dpp >= 3.0 else 'FAIL'}")
    print(f"  [sensitivity, BTC-only day set: AB slope {1e4*rAB[chop_btc].mean():.2f} bp/d; "
          f"C contribution at wC=0.10: {100*(( (0.9*rAB+0.1*rC)[chop_btc].mean()) - rAB[chop_btc].mean())*ANN:+.2f}pp]")
    print("\n--- Pre-reg gate-rule cross-check (PRE_REG §2.1 'IS 上限高者' = g4 per C0): g4_96_25")
    sh_g4 = sharpe((1 - 0.10) * rAB + 0.10 * rCg4)
    dpp_g4 = 100 * (((0.9 * rAB + 0.1 * rCg4)[chop_any].mean()) - base_slope) * ANN
    print(f"  wC=0.10: Sharpe={sh_g4:.3f} (vs AB {sharpe(rAB):.3f}) "
          f"chop slope improvement {dpp_g4:+.2f}pp ann -> "
          f"{'PASS' if sh_g4 >= sharpe(rAB) and dpp_g4 >= 3.0 else 'FAIL'}")

    print("\n=== C standalone economics (winner g2_96_25) ===")
    for tag, zp in (("IS 21-23", ROOT / "research_chop/results/chop_c1_is_g2_96_25.zip"),
                    ("OS 24-26", ROOT / "research_chop/results/chop_c1_os_g2_96_25.zip"),
                    ("OS 24-26 g4 xchk", ROOT / "research_chop/results/chop_c1_os_g4_96_25.zip")):
        e = econ(zp)
        print(f"  {tag}: trades={e['trades']} win%={e['win%']:.1f} "
              f"avg_net={e['avg_net_usdt']:.2f} USDT ({e['avg_net_bps_notional']:.1f}bp of notional) "
              f"fees={e['fees_usdt']:.0f} funding={e['funding_usdt']:.0f} "
              f"(fee+fnd)/grosswin={e['fee+fnd/grosswin']:.3f} "
              f"profit={e['profit_total%']:.1f}% sharpe={e['sharpe_ft']:.2f} "
              f"maxdd={e['maxdd%']:.1f}% edge_thin={e['edge_thin']}")

    tbl.round(4).to_csv(ROOT / "research_chop/logs/c1_os_adjudication.csv", index=False)
    print("\nsaved -> research_chop/logs/c1_os_adjudication.csv")


if __name__ == "__main__":
    main()
