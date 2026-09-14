"""PRT02: extract mark-to-market daily equity curves from sleeve zips' wallet feathers.

Wallet feather = per-candle wallet snapshot (all currencies, total_quote in USDT).
Daily equity for day D = total_quote sum across currencies at the LAST candle closing
within (D-1 24:00, D 24:00]  (row timestamps are candle-close labels, so subtract 1us
before flooring).  Returns anchored at initial wallet 10000.

Usage: python prt02_equity.py [out_csv] [B_zip_name_or_-]
Writes daily equity + diagnostics; sleeves with missing zips are skipped.
"""
import json, glob, os, sys, zipfile
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, r"research_deepen\portfolio\results\daily_equity.csv")
B_ZIP = sys.argv[2] if len(sys.argv) > 2 else "-"   # optional: rerun zip filename for sleeve B

SLEEVES = {
    "A": os.path.join(ROOT, "user_data", "backtest_results", "opt4_VolatilitySystem_12p_is.zip"),
    "N": os.path.join(ROOT, "user_data", "backtest_results", "opt7_lite_tc3_12p_is.zip"),
    "S": os.path.join(ROOT, "user_data", "backtest_results", "opt7_pool12_A8_OPT7_SuperDD_A.zip"),
}
if B_ZIP != "-":
    SLEEVES["B"] = B_ZIP if os.path.isabs(B_ZIP) else os.path.join(
        ROOT, "research_deepen", "portfolio", "results", B_ZIP)

START, END = "2021-01-01", "2023-12-31"
INIT = 10000.0


def zip_wallet_df(zname):
    with zipfile.ZipFile(zname) as f:
        wf = [n for n in f.namelist() if n.endswith("_wallet.feather")]
        if not wf:
            raise RuntimeError(f"no wallet feather in {zname}")
        import io
        return pd.read_feather(io.BytesIO(f.read(wf[0]))), f, wf[0]


def main_json_from_zip(f):
    mains = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n]
    return json.loads(f.read(mains[0]))


def daily_equity_from_wallet(w):
    w = w.copy()
    w["date"] = pd.to_datetime(w["date"], utc=True)
    eq = w.groupby("date")["total_quote"].sum().sort_index()
    day = (eq.index - pd.Timedelta(microseconds=1)).floor("D")
    deq = eq.groupby(day).last()
    deq = deq[(deq.index >= pd.Timestamp(START, tz="UTC")) & (deq.index <= pd.Timestamp(END, tz="UTC"))]
    return deq


def diag(zname, deq):
    """Cross-check wallet equity vs freqtrade's own daily_profit (realized) and totals."""
    with zipfile.ZipFile(zname) as f:
        d = main_json_from_zip(f)
    out = {}
    for name, s in d["strategy"].items():
        dp = pd.DataFrame(s["daily_profit"], columns=["date", "profit"])
        dp["date"] = pd.to_datetime(dp["date"], utc=True)
        dp = dp.set_index("date")["profit"]
        dp = dp[(dp.index >= deq.index.min()) & (dp.index <= deq.index.max())]
        dly_wallet = deq.diff().fillna(deq.iloc[0] - INIT)
        joined = pd.DataFrame({"wallet": dly_wallet, "realized": dp}).fillna(0.0)
        out[name] = dict(
            trades=len(s["trades"]),
            profit_total_pct=round(s["profit_total"] * 100, 2),
            maxdd_account_pct=round(s["max_drawdown_account"] * 100, 2),
            wallet_final=round(deq.iloc[-1], 1),
            wallet_total_pct=round(deq.iloc[-1] / INIT * 100 - 100, 2),
            wallet_daily_minus_realized_mean=round((joined["wallet"] - joined["realized"]).mean(), 2),
            corr_daily_wallet_vs_realized=round(joined["wallet"].corr(joined["realized"]), 3),
            n_days=len(deq),
        )
    return out


frames, diags = {}, {}
for tag, z in SLEEVES.items():
    try:
        w, f, _ = zip_wallet_df(z)
        deq = daily_equity_from_wallet(w)
        frames[tag] = deq
        diags[tag] = diag(z, deq)
        print(f"[{tag}] {z}: {len(deq)} days, final {deq.iloc[-1]:.1f}")
    except Exception as e:
        print(f"[{tag}] {z}: SKIP ({e})")

df = pd.DataFrame(frames)
df.index.name = "date"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
df.to_csv(OUT)
print("\nsaved", OUT)
print(df.describe().to_string())
for tag, dd in diags.items():
    for k, v in dd.items():
        print(tag, k, v)
