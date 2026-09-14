"""PRT05: assemble the portfolio-agent dataset.

Two consistent daily-frequency equity conventions per sleeve (A/B/N/S), 2021-01-01..2023-12-31:
  realized : equity(t) = 10000 + sum(profit_abs of trades closed <= t)  [uniform, from trades JSON]
  mtm      : prt03 reconstruction (hourly mark-to-market, reconciled to profit_abs at close)

Outputs (research_deepen/portfolio/results/):
  returns_daily.csv    date, <sleeve>_ret_realized, <sleeve>_ret_mtm
  returns_monthly.csv  month, <sleeve>_mom_realized, <sleeve>_mom_mtm
  summary_sleeves.csv  per-sleeve headline metrics on both conventions
"""
import json, os, zipfile
import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, r"research_deepen\portfolio\results")
INIT = 10000.0
IDX = pd.date_range("2021-01-01", "2023-12-31", freq="D", tz="UTC")

ZIPS = {
    "A": ("user_data/backtest_results/opt4_VolatilitySystem_12p_is.zip",
          "OPT4 frozen form (OPT4_C2 params==OPT4: 2.0/2.0+atr08+ts60), 12p MOT4 1h"),
    "N": ("user_data/backtest_results/opt7_lite_tc3_12p_is.zip",
          "OPT7_NFILite frozen, 12p MOT6 5m"),
    "S": ("user_data/backtest_results/opt7_pool12_A8_OPT7_SuperDD_A.zip",
          "OPT7_SuperDD_A frozen 8xATR, 12p MOT3 1h"),
    "B": ("research_deepen/portfolio/results/prt_B_momregime15mlb21_full.zip",
          "PRT rerun of frozen OPT2_MomRegime15mLb21 (mpw45/tolm3/abs), 12p MOT3 15m, full window"),
}


def realized_daily(zrel):
    z = os.path.join(ROOT, zrel)
    with zipfile.ZipFile(z) as f:
        m = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n][0]
        d = json.loads(f.read(m))
    s = list(d["strategy"].values())[0]
    tr = pd.DataFrame([(pd.to_datetime(t["close_date"]), float(t["profit_abs"])) for t in s["trades"]],
                      columns=["cd", "pnl"])
    day = (tr["cd"] - pd.Timedelta(microseconds=1)).dt.floor("D")
    pnl_d = tr.groupby(day)["pnl"].sum()
    pnl_d = pnl_d[(pnl_d.index >= IDX[0]) & (pnl_d.index <= IDX[-1])]
    eq = INIT + pnl_d.cumsum().reindex(IDX).ffill().fillna(0)
    return eq


def metrics(eq):
    ret = eq.pct_change().fillna(eq.iloc[0] / INIT - 1)
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(365)
    dd = (eq / eq.cummax() - 1).min()
    return dict(total=eq.iloc[-1] / INIT - 1, cagr=cagr, annvol=vol,
                sharpe=(ret.mean() * 365) / vol if vol > 0 else np.nan,
                maxdd=dd, calmar=cagr / abs(dd) if dd < 0 else np.nan)


def main():
    out_r, out_m = {}, {}
    rows = []
    for tag, (zrel, desc) in ZIPS.items():
        rz = realized_daily(zrel)
        mt = pd.read_csv(os.path.join(RES, f"mtm_daily_{tag}.csv"), index_col=0).iloc[:, 0]
        mt.index = pd.to_datetime(mt.index, utc=True)
        assert (rz.index == mt.index).all(), tag
        out_r[tag] = rz.pct_change().fillna(rz.iloc[0] / INIT - 1)
        out_m[tag] = mt.pct_change().fillna(mt.iloc[0] / INIT - 1)
        for conv, eq in (("realized", rz), ("mtm", mt)):
            m = metrics(eq)
            rows.append(dict(sleeve=tag, conv=conv, **{k: round(v, 4) for k, v in m.items()}))
        print(tag, desc)

    rd = pd.DataFrame(out_r); rd.index.name = "date"
    rm = pd.DataFrame(out_m); rm.index.name = "date"
    rd.to_csv(os.path.join(RES, "returns_daily.csv"))
    rm.to_csv(os.path.join(RES, "returns_mtm_daily.csv"))
    # monthly compounded
    for df, name in ((rd, "returns_monthly.csv"), (rm, "returns_mtm_monthly.csv")):
        m = (1 + df).groupby(df.index.to_period("M")).prod() - 1
        m.index = m.index.astype(str)
        m.index.name = "month"
        m.to_csv(os.path.join(RES, name))
    sm = pd.DataFrame(rows)
    sm.to_csv(os.path.join(RES, "summary_sleeves.csv"), index=False)
    print(sm.to_string())


if __name__ == "__main__":
    main()
