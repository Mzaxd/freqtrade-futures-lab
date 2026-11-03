#!/usr/bin/env python3
"""OPT9 guard-check: compare an OPT9 result zip against the OPT4 baseline zip.

Pre-registered guards:
  G1  maxDD <= 16.4%  (baseline 15.92% + 0.5pp)
  G2  six half-year slices (by trade open_date) all positive
  G3  top-20 winner profit sum >= 95% of baseline's

Usage: opt9_guards.py BASELINE.zip CANDIDATE.zip
(stdlib only; run with any python3)
"""
import json
import sys
import zipfile


def load(zippath, strategy=None):
    with zipfile.ZipFile(zippath) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "_config" not in n]
        name = sorted(names)[0]
        d = json.loads(z.read(name))
    key = strategy or next(iter(d["strategy"]))
    return d["strategy"][key]


def metrics(s):
    return {
        "trades": s["total_trades"],
        "profit_pct": s["profit_total"] * 100,
        "profit_abs": s["profit_total_abs"],
        "maxdd_pct": s["max_drawdown_account"] * 100,
        "sharpe": s["sharpe"],
        "pf": s["profit_factor"],
        "wins": s["wins"],
        "losses": s["losses"],
    }


def half_year_slices(trades):
    out = {}
    for t in trades:
        k = t["open_date"][:4] + ("H1" if int(t["open_date"][5:7]) <= 6 else "H2")
        out.setdefault(k, 0.0)
        out[k] += t["profit_abs"]
    return dict(sorted(out.items()))


def top20_sum(trades):
    return sum(t["profit_abs"] for t in sorted(trades, key=lambda x: -x["profit_abs"])[:20])


def main():
    base_zip, cand_zip = sys.argv[1], sys.argv[2]
    b, c = load(base_zip), load(cand_zip)
    mb, mc = metrics(b), metrics(c)
    sb, sc = half_year_slices(b["trades"]), half_year_slices(c["trades"])
    t20b, t20c = top20_sum(b["trades"]), top20_sum(c["trades"])

    print(f"{'metric':<14}{'baseline':>14}{'candidate':>14}{'delta':>12}")
    for k in mb:
        d = mc[k] - mb[k]
        print(f"{k:<14}{mb[k]:>14.2f}{mc[k]:>14.2f}{d:>+12.2f}")
    print("\nhalf-year slices (profit_abs):")
    for k in sorted(set(sb) | set(sc)):
        print(f"  {k}: base {sb.get(k, 0):>10.0f}  cand {sc.get(k, 0):>10.0f}")
    print(f"\ntop-20 winners: base {t20b:.0f}  cand {t20c:.0f}  "
          f"({t20c / t20b * 100:.1f}% of baseline)")

    g1 = mc["maxdd_pct"] <= 16.4
    g2 = all(v > 0 for v in sc.values()) and len(sc) >= 6
    g3 = t20c >= 0.95 * t20b
    print(f"\nG1 maxDD<=16.4: {'PASS' if g1 else 'FAIL'}"
          f" | G2 slices all>0: {'PASS' if g2 else 'FAIL'}"
          f" | G3 top20>=95%: {'PASS' if g3 else 'FAIL'}")
    sys.exit(0 if (g1 and g2 and g3) else 1)


if __name__ == "__main__":
    main()
