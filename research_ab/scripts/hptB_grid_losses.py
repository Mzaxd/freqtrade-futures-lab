# hptB_grid_losses.py — aggregate the Hyperopt-B mini-grid IS results.
# For every research_ab/results/hptB_cell_<X>_IS.zip (and the frozen baseline
# hptB_baseline_IS.zip) compute, from the TRADES in the zip:
#   * SharpeHyperOptLossDaily replica (daily summed profit_ratio minus 0.0005
#     slippage per trade, annualized)  — identical formula to freqtrade 2026.8
#   * CalmarHyperOptLoss replica (freqtrade.data.metrics.calculate_calmar)
#   * trade count, total profit, freqtrade account drawdown
#   * MTM (hourly mark-to-market via dp_mtm) IS-window total ret / maxDD / Sharpe
# Also merges the 6 archived hyperopt epochs (3 unique cells) for reference.
# Usage: python hptB_grid_losses.py   (writes research_ab/results/hptB_grid_losses.csv)
import glob
import json
import math
import zipfile
from pathlib import Path

import pandas as pd

import freqtrade.data.metrics as ftm

BASE = Path(r"D:\Code\AIQuant\freqtrade-futures-lab")
RESULTS = BASE / "research_ab" / "results"

CELL_PARAMS = {
    "baseline": dict(regime_sma=100, per_coin_sma=50, regime_tolerance=-0.03,
                     funding_max_p=0.0005, max_position_weight=0.45),
    "R50": dict(regime_sma=50), "R75": dict(regime_sma=75),
    "R125": dict(regime_sma=125), "R150": dict(regime_sma=150),
    "P20": dict(per_coin_sma=20), "P30": dict(per_coin_sma=30),
    "P75": dict(per_coin_sma=75), "P100": dict(per_coin_sma=100),
    "Tm02": dict(regime_tolerance=-0.02), "T0": dict(regime_tolerance=0.0),
    "Tp02": dict(regime_tolerance=0.02),
    "F03": dict(funding_max_p=0.0003), "F08": dict(funding_max_p=0.0008),
    "F10": dict(funding_max_p=1.0),
    "M30": dict(max_position_weight=0.30), "M60": dict(max_position_weight=0.60),
}


def load_zip(path: str):
    with zipfile.ZipFile(path) as f:
        main = [n for n in f.namelist() if n.endswith(".json")
                and "_config" not in n and not n.endswith("meta.json")][0]
        d = json.loads(f.read(main))
    s = list(d["strategy"].values())[0]
    tr = pd.DataFrame(s["trades"])
    tr["close_date"] = pd.to_datetime(tr["close_date"], utc=True)
    tr["profit_ratio"] = tr["profit_ratio"].astype(float)
    tr["profit_abs"] = tr["profit_abs"].astype(float)
    return s, tr


def sharpe_loss(tr: pd.DataFrame) -> float:
    res = tr.copy()
    res["pra"] = res["profit_ratio"] - 0.0005
    idx = pd.date_range(res["close_date"].min().normalize(),
                        res["close_date"].max().normalize(), freq="1D")
    sd = res.resample("1D", on="close_date").agg({"pra": "sum"}).reindex(idx).fillna(0)
    v = sd["pra"]
    if v.std() == 0:
        return -20.0
    return float(-(v.mean() / v.std() * math.sqrt(365)))


def calmar_loss(tr: pd.DataFrame) -> float:
    try:
        c = ftm.calculate_calmar(tr, tr["close_date"].min(), tr["close_date"].max(), 10000.0)
    except Exception:
        return 0.0
    return float(-c)


def main() -> None:
    import sys
    sys.path.insert(0, str(BASE / "research_deepen" / "_dispatcher" / "scripts"))
    sys.path.insert(0, str(BASE / "research_ab" / "scripts"))
    import dp_mtm
    from hptB_mtm_metrics import mtm_metrics  # same scripts dir

    rows = []
    jobs = [("baseline", str(RESULTS / "hptB_baseline_IS.zip"))]
    for z in sorted(glob.glob(str(RESULTS / "hptB_cell_*_IS.zip"))):
        cell = Path(z).stem.replace("hptB_cell_", "").replace("_IS", "")
        jobs.append((cell, z))
    for cell, z in jobs:
        try:
            s, tr = load_zip(z)
        except Exception as e:
            print(f"{cell}: load error {e}")
            continue
        m = None
        try:
            deq, _ = dp_mtm.reconstruct_window(z, pd.Timestamp("2021-01-01", tz="UTC"),
                                               pd.Timestamp("2024-01-01", tz="UTC"))
            m = mtm_metrics(deq)
        except Exception as e:
            print(f"{cell}: mtm error {e}")
        rows.append(dict(
            cell=cell, trades=s["total_trades"],
            profit_pct=s["profit_total"] * 100,
            ft_dd_pct=s.get("max_drawdown_account", float("nan")) * 100,
            sharpe_loss=sharpe_loss(tr), calmar_loss=calmar_loss(tr),
            mtm_ret_pct=m["total_ret"] * 100 if m else float("nan"),
            mtm_maxdd_pct=m["maxdd"] * 100 if m else float("nan"),
            mtm_sharpe=m["sharpe"] if m else float("nan"),
            zip=Path(z).name,
        ))

    # archived hyperopt epochs (3 unique cells, IS window, same engine)
    for tag, f in [("hptS", RESULTS / "hptB_sharpe_epochs.fthypt"),
                   ("hptC", RESULTS / "hptB_calmar_epochs.fthypt")]:
        if not f.exists():
            continue
        for line in open(f, encoding="utf-8"):
            d = json.loads(line)
            rm = d["results_metrics"]
            rows.append(dict(
                cell=f"{tag}_ep{d['current_epoch']}", trades=rm["total_trades"],
                profit_pct=rm["profit_total"] * 100,
                ft_dd_pct=rm.get("max_drawdown_account", float("nan")) * 100,
                sharpe_loss=float("nan") if tag == "hptC" else d["loss"],
                calmar_loss=float("nan") if tag == "hptS" else d["loss"],
                mtm_ret_pct=float("nan"), mtm_maxdd_pct=float("nan"),
                mtm_sharpe=float("nan"),
                zip=json.dumps(d["params_dict"]),
            ))

    df = pd.DataFrame(rows).sort_values("sharpe_loss")
    df.to_csv(RESULTS / "hptB_grid_losses.csv", index=False)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False, float_format=lambda x: f"{x:9.3f}"))


if __name__ == "__main__":
    main()
