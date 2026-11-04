# hptB_mtm_metrics.py — three-window MTM metrics from backtest zips (Hyperopt-B).
# Uses the dispatcher MTM reconstruction (dp_mtm.py, hourly MTM, avg-cost accounting)
# so numbers are directly comparable with the sleeve-B baseline quote
# (+4076% / maxDD -29.3% from mtm_daily_B3.csv).
# Usage: python hptB_mtm_metrics.py <zip> [<zip> ...]
# Windows are fixed: IS 2021-01-01..2024-01-01, 24-26 2024-01-02..2026-09-13,
# full 2021-01-01..2026-09-13 (hourly grid exclusive of end).
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r"D:\Code\AIQuant\freqtrade-futures-lab\research_deepen\_dispatcher\scripts")
import dp_mtm  # noqa: E402

WINDOWS = {
    "IS": ("2021-01-01", "2024-01-01"),
    "24-26": ("2024-01-02", "2026-09-13"),
    "full": ("2021-01-01", "2026-09-13"),
}


def mtm_metrics(deq: pd.Series) -> dict:
    eq = deq.astype(float)
    ret = eq.iloc[-1] / eq.iloc[0] - 1.0
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0
    dd = (eq / eq.cummax() - 1.0).min()
    r = eq.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * np.sqrt(365.0)) if len(r) > 2 and r.std() > 0 else float("nan")
    return dict(total_ret=ret, years=years, cagr=cagr, maxdd=float(dd), sharpe=sharpe)


def freqtrade_stats(zip_path: str) -> dict:
    import json
    import zipfile
    with zipfile.ZipFile(zip_path) as f:
        main = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n and not n.endswith("meta.json")][0]
        d = json.loads(f.read(main))
    out = {}
    for k, s in d["strategy"].items():
        out[k] = dict(
            trades=s["total_trades"],
            profit_pct=s["profit_total"] * 100,
            ft_maxdd_acct=s.get("max_drawdown_account", float("nan")) * 100,
            ft_sharpe=s.get("sharpe", float("nan")),
            timerange=s.get("timerange"),
        )
    return out


if __name__ == "__main__":
    for z in sys.argv[1:]:
        print(f"\n=== {z} ===")
        try:
            print("freqtrade-native:", freqtrade_stats(z))
        except Exception as e:
            print("  freqtrade stats error:", e)
        for wname, (s, e) in WINDOWS.items():
            start = pd.Timestamp(s, tz="UTC")
            end = pd.Timestamp(e, tz="UTC")
            try:
                deq, diag = dp_mtm.reconstruct_window(z, start, end)
            except Exception as ex:
                print(f"  {wname}: MTM error {ex}")
                continue
            if len(deq) == 0:
                print(f"  {wname}: no MTM days")
                continue
            series = deq.iloc[:, 0] if isinstance(deq, pd.DataFrame) else deq
            m = mtm_metrics(series)
            print(f"  {wname:5s} days={len(deq):5d} ret={m['total_ret']*100:12.1f}% "
                  f"CAGR={m['cagr']*100:6.1f}% maxDD={m['maxdd']*100:6.1f}% "
                  f"sharpe={m['sharpe']:5.2f}")
