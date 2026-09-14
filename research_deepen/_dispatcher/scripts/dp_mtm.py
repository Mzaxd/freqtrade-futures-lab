# dp_mtm.py — dispatcher port of PRT's prt03_mtm.py with CLI window args.
# Attribution: reconstruction logic (per-trade hourly MTM, average-cost
# accounting, reconciliation checks) is PRT agent's work, unchanged; only the
# hardcoded 2021-2023 window is parameterized for the 2024-26 diagnostic.
# Usage: python dp_mtm.py <zipname> <tag> <START> <END> [out_csv]
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
sys.path.insert(0, os.path.join(ROOT, "research_deepen", "portfolio", "scripts"))
import prt03_mtm as base  # noqa: E402

DATA = os.path.join(ROOT, r"user_data\data\binance\futures")
INIT = 10000.0


def reconstruct_window(zname, start, end):
    base.START = start
    base.END = end
    with zipfile.ZipFile(zname) as f:
        main = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n][0]
        d = json.loads(f.read(main))
    s = list(d["strategy"].values())[0]
    trades = s["trades"]

    cl = pd.DataFrame([(pd.to_datetime(t["close_date"]), float(t["profit_abs"])) for t in trades],
                      columns=["ts", "pnl"]).sort_values("ts")
    cash_steps = cl.groupby("ts")["pnl"].sum().cumsum() + INIT

    pieces, recon_err = [], []
    for t in trades:
        path, _ = base.trade_path(t)
        if path is None:
            continue
        recon_err.append(abs(path.iloc[-1] - float(t["profit_abs"])))
        pieces.append(path)

    idx = pd.date_range(start, end, freq="1h", inclusive="left")
    cash_h = cash_steps.reindex(idx.union(cash_steps.index)).ffill().reindex(idx)
    cash_h.iloc[0] = INIT
    cash_h = cash_h.ffill().fillna(INIT)
    unreal = pd.concat(pieces).groupby(level=0).sum().sort_index() if pieces else pd.Series(0.0, index=idx)
    un_h = unreal.reindex(idx.union(unreal.index)).fillna(0.0).groupby(level=0).sum().reindex(idx).fillna(0.0)
    eq_h = (cash_h + un_h).iloc[1:]
    day = (eq_h.index - pd.Timedelta(microseconds=1)).floor("D")
    deq = eq_h.groupby(day).last()
    deq = deq[(deq.index >= start) & (deq.index <= end)]
    return deq, dict(n_trades=len(trades),
                     recon_err_p95=round(float(np.percentile(recon_err, 95)), 2) if recon_err else None,
                     recon_err_max=round(max(recon_err), 2) if recon_err else None,
                     freqtrade_total=round(INIT + float(cl["pnl"].sum()), 1))


if __name__ == "__main__":
    zname, tag, start_s, end_s = sys.argv[1:5]
    out = sys.argv[5] if len(sys.argv) > 5 else os.path.join(
        ROOT, "research_deepen", "_dispatcher", "results", f"mtm_daily_{tag}_2426.csv")
    start = pd.Timestamp(start_s, tz="UTC")
    end = pd.Timestamp(end_s, tz="UTC")
    deq, diag = reconstruct_window(zname, start, end)
    deq.to_csv(out, header=[f"eq_{tag}"])
    print(tag, zname, "->", out)
    for k, v in diag.items():
        print(" ", k, v)
    print("  daily n:", len(deq), "range:",
          deq.index[0].date() if len(deq) else "-", "->", deq.index[-1].date() if len(deq) else "-")
