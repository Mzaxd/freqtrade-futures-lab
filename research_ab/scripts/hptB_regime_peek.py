# hptB_regime_peek.py — REGIME_SMA "IS-peeking" check for Hyperopt-B (sleeve B).
#
# Question (task brief): if the best REGIME_SMA differs from the pre-registered
# 100, is that just moving the 2022-bear exit/entry dates around INSIDE the IS
# window (in-sample cycle peeking), and does the signal difference persist in
# the 24-26 disclosure window?
#
# Exact strategy semantics (OPT1_MomRegime15mFast._compute_xs):
#   known  = daily_close.shift(1)                      # yesterday's close
#   ron_d  = known > known.rolling(REGIME_SMA).mean() * (1 - REGIME_TOLERANCE)
# So the day-D signal uses only closes up to D-1. Replicated here on daily bars.
#
# Usage: python hptB_regime_peek.py <best_sma> <best_tol> [out_png]
import sys

import pandas as pd

FEATHER = (r"D:\Code\AIQuant\freqtrade-futures-lab"
           r"\user_data\data\binance\futures\BTC_USDT_USDT-1d-futures.feather")

IS_END = pd.Timestamp("2024-01-01", tz="UTC")


def risk_on(close: pd.Series, sma: int, tol: float) -> pd.Series:
    known = close.shift(1)
    return known > known.rolling(sma).mean() * (1.0 - tol)


def main(best_sma: int, best_tol: float, out_png: str | None) -> None:
    d = pd.read_feather(FEATHER)
    d["date"] = pd.to_datetime(d["date"], utc=True)
    close = d.set_index("date")["close"]

    base = risk_on(close, 100, -0.03)          # frozen sleeve-B baseline
    best = risk_on(close, best_sma, best_tol)

    df = pd.DataFrame({"close": close, "base": base, "best": best}).dropna()
    df["diverge"] = df["base"] != df["best"]
    df["ret"] = close.pct_change()

    print(f"baseline: SMA100 tol=-0.03   best: SMA{best_sma} tol={best_tol}")
    yearly = df.groupby(df.index.year).agg(
        days=("close", "size"),
        base_on=("base", "sum"),
        best_on=("best", "sum"),
        diverge=("diverge", "sum"),
    )
    print("\nper-year: days | risk-on days (base vs best) | divergent days")
    print(yearly.to_string())

    # divergent-day direction: base ON & best OFF (bear-avoid) vs base OFF & best ON
    d_only_base_on = df["base"] & ~df["best"]
    d_only_best_on = df["best"] & ~df["base"]
    for name, mask, label in [
        ("IS 2021-2023", df.index < IS_END, "in-sample"),
        ("24-26", df.index >= IS_END, "disclosure"),
    ]:
        sel = df[mask]
        m1 = sel["base"] & ~sel["best"]
        m2 = sel["best"] & ~sel["base"]
        for lbl, m in [("base ON, best OFF (exposure removed)", m1),
                       ("best ON, base OFF (exposure added)", m2)]:
            if m.sum():
                r = sel.loc[m, "ret"]
                print(f"\n{name} {lbl}: {int(m.sum())} days, "
                      f"mean next-day BTC ret {r.mean()*100:+.3f}%/d "
                      f"(cum {((1+r).prod()-1)*100:+.1f}%)")
            else:
                print(f"\n{name} {lbl}: 0 days")

    # switch dates
    for name, mask in [("IS", df.index < IS_END), ("24-26", df.index >= IS_END)]:
        sub = df[mask]
        sw = sub[(sub["base"].diff() != 0) | (sub["best"].diff() != 0)]
        print(f"\n{name} regime switches (date, base, best):")
        for ts, row in sw.iterrows():
            mark = "  <-- differs" if row["base"] != row["best"] else ""
            print(f"  {ts.date()}  base={'ON ' if row['base'] else 'OFF'} "
                  f"best={'ON ' if row['best'] else 'OFF'}{mark}")

    if out_png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(df.index, df["close"], lw=0.8, color="black", label="BTC close")
        ax.plot(df.index, close.rolling(100).mean().shift(1), lw=1.0, color="tab:blue",
                label="SMA100 (baseline switch)")
        ax.plot(df.index, close.rolling(best_sma).mean().shift(1), lw=1.0, color="tab:red",
                label=f"SMA{best_sma} (hyperopt best)")
        ax.set_yscale("log")
        div = df["diverge"]
        ax.fill_between(df.index, 0, 1, where=div, transform=ax.get_xaxis_transform(),
                        color="orange", alpha=0.25, label="signal differs")
        ax.axvline(IS_END, color="gray", ls="--", lw=1)
        ax.text(IS_END, ax.get_ylim()[0], " IS|24-26 ", va="bottom")
        ax.legend(loc="upper left")
        ax.set_title(f"Sleeve B regime switch: baseline SMA100/tol-0.03 vs best SMA{best_sma}/tol{best_tol}")
        fig.tight_layout()
        fig.savefig(out_png, dpi=130)
        print(f"\nsaved {out_png}")


if __name__ == "__main__":
    best_sma = int(sys.argv[1])
    best_tol = float(sys.argv[2])
    out_png = sys.argv[3] if len(sys.argv) > 3 else None
    main(best_sma, best_tol, out_png)
