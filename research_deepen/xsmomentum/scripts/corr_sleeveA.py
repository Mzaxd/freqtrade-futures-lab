# -*- coding: utf-8 -*-
"""组合价值评估：XS(选中参数, LS) 与 Sleeve A (OPT4=XS_OPT4Ref 重跑) 的月度收益相关性，2021-01→2023-12。
输入: results/daily_is.csv, results/daily_val.csv, results/xs_opt4ref_2021_2023.zip
输出: results/corr_sleeveA.json
"""
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]


def xs_monthly() -> pd.Series:
    is_d = pd.read_csv(HERE / "results" / "daily_is.csv", index_col=0, parse_dates=True)
    val_d = pd.read_csv(HERE / "results" / "daily_val.csv", index_col=0, parse_dates=True)
    sel = json.load(open(HERE / "results" / "plateau_selection.json", encoding="utf-8"))["selected"]
    key_is = f"lb{sel['lookback']}_sk{sel['skip']}_h{sel['hold']}_LS"
    daily = pd.concat([is_d[key_is], val_d["LS"]]).sort_index()
    m = (1.0 + daily).resample("ME").prod() - 1.0
    m.index = m.index.tz_localize(None)
    return m[(m.index >= pd.Timestamp("2021-01-01")) & (m.index <= pd.Timestamp("2023-12-31"))]


def opt4_monthly() -> pd.Series:
    zpath = HERE / "results" / "xs_opt4ref_2021_2023.zip"
    with zipfile.ZipFile(zpath) as z:
        jname = [n for n in z.namelist()
                 if n.endswith(".json") and "config" not in n and "market" not in n][0]
        data = json.loads(z.read(jname))
        s = data["strategy"]["XS_OPT4Ref"]
        rows = s["periodic_breakdown"]["month"]
    ser = pd.Series({pd.Timestamp(r["date_ts"], unit="ms", tz="UTC"): r["profit_abs"] for r in rows})
    ser.index = ser.index.tz_localize(None) if ser.index.tz is not None else ser.index
    return ser[(ser.index >= pd.Timestamp("2021-01-01")) & (ser.index <= pd.Timestamp("2023-12-31"))]


def main():
    xs = xs_monthly()
    a = opt4_monthly()
    # 对齐到月末
    xs.index = xs.index.tz_localize(None) if xs.index.tz is not None else xs.index
    df = pd.DataFrame({"xs_ret": xs, "opt4_pnl": a}).dropna()
    corr_p = float(df["xs_ret"].corr(df["opt4_pnl"]))
    corr_s = float(df["xs_ret"].corr(df["opt4_pnl"], method="spearman"))
    out = {
        "n_months": int(len(df)),
        "pearson": corr_p,
        "spearman": corr_s,
        "xs_monthly_mean": float(df["xs_ret"].mean()),
        "xs_monthly_std": float(df["xs_ret"].std()),
        "opt4_monthly_mean_usdt": float(df["opt4_pnl"].mean()),
        "opt4_monthly_std_usdt": float(df["opt4_pnl"].std()),
        "threshold": 0.3,
        "criterion4_pass": bool(abs(corr_p) < 0.3),
        "window": "2021-01..2023-12",
    }
    (HERE / "results" / "corr_sleeveA.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    df.to_csv(HERE / "results" / "monthly_xs_vs_opt4.csv")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
