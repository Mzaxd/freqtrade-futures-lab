"""CRASH portfolio synthesis: 70/30 A+B from wallet curves (CONTEXT §6 standard).

CLI:
  python -I synth_portfolio.py <A_zip> <B_zip> [--a ARL_2x] [--b OPT2_MomRegime15mLb21]
Prints yearly returns, from-peak maxDD, 30d-rolling DD min for the portfolio.
Anchors each sleeve's final value to the JSON profit_total_abs (feather-tail pitfall).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wallet_lib import LAB, anchor_final, load_wallet


def synth(a_zip: Path, b_zip: Path, a_name="ARL_2x", b_name="OPT2_MomRegime15mLb21",
          wa=0.7, wb=0.3, anchor=True):
    wa_curve = load_wallet(a_zip, a_name)
    wb_curve = load_wallet(b_zip, b_name)
    if anchor:
        for curve, zp, nm in ((wa_curve, a_zip, a_name), (wb_curve, b_zip, b_name)):
            start, final = anchor_final(zp, nm)
            cur_end = float(curve.iloc[-1])
            if cur_end > 0:
                curve.iloc[-1] = final  # anchor tail (feather misses last-candle settles)
    # hourly grid union, ffill, weighted sum of normalized curves
    h = wa_curve.resample("h").last().ffill()
    hb = wb_curve.resample("h").last().ffill()
    idx = h.index.union(hb.index)
    a = (h / float(h.iloc[0])).reindex(idx).ffill()
    b = (hb / float(hb.iloc[0])).reindex(idx).ffill()
    port = wa * a + wb * b
    return port


def report(port: pd.Series, label: str):
    d = port.resample("D").last().dropna()
    print(f"--- {label} ---")
    print("start/end:", d.index[0].date(), d.index[-1].date())
    for y, g in d.groupby(d.index.year):
        print(f"  {y}: {(g.iloc[-1] / g.iloc[0] - 1) * 100:+.1f}%")
    fp = d / d.cummax() - 1
    dd30 = d / d.rolling(30).max() - 1
    print(f"  from-peak maxDD {fp.min() * 100:.1f}% on {fp.idxmin().date()}")
    print(f"  30d-rolling DD min {dd30.min() * 100:.1f}% on {dd30.idxmin().date()}")
    return d


if __name__ == "__main__":
    a_zip = Path(sys.argv[1]) if not str(sys.argv[1]).startswith("--") else None
    b_zip = Path(sys.argv[2])
    a_name = "ARL_2x"
    b_name = "OPT2_MomRegime15mLb21"
    args = sys.argv[3:]
    if "--a" in args:
        a_name = args[args.index("--a") + 1]
    if "--b" in args:
        b_name = args[args.index("--b") + 1]
    port = synth(a_zip, b_zip, a_name, b_name)
    report(port, f"70/30 {a_name}+{b_name}")
