"""r3_is_select.py — IS selection metrics for WS-R3 variants.

Loads each IS zip via dp_mtm's reconstruct_window (same reconstruction as the
baseline curves), builds daily equity, and computes:
  total_ret   = eq_end/10000 - 1
  maxDD       = min(eq/peak - 1)  (daily close curve)
  Calmar      = total_ret / |maxDD|   (pre-registered selection metric)
  retention   = total_ret / baseline_IS_total_ret
Baseline IS = slice of the full-window R3BASE reconstruction (dp_mtm on the
full zip with END=2024-01-01; open trades carried as MTM, no force close).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(r"D:\Code\AIQuant\freqtrade-futures-lab",
                                "research_deepen", "_dispatcher", "scripts"))
import dp_mtm  # noqa: E402

IS_S = pd.Timestamp("2021-01-01", tz="UTC")
IS_E = pd.Timestamp("2024-01-01", tz="UTC")

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
RES = os.path.join(ROOT, "research_chop", "results")
INIT = 10000.0

VARIANTS = ["R3_G1h", "R3_G2h", "R3_G4h",
            "R3_C3h_N2_D14", "R3_C3h_N2_D30", "R3_C3h_N3_D14",
            "R3_C3h_N3_D30", "R3_C3h_N4_D14", "R3_C3h_N4_D30"]
EXTRA = sys.argv[1:]   # additional zips (tags) to include, e.g. C3p winner


def metrics(deq):
    eq = deq / INIT
    peak = eq.cummax()
    dd = (eq / peak - 1.0).min()
    total = eq.iloc[-1] - 1.0
    return total, dd, total / abs(dd)


rows = []
base_deq, _ = dp_mtm.reconstruct_window(os.path.join(RES, "R3_base_ARL2x_full.zip"),
                                        IS_S, IS_E)
bt, bdd, bcal = metrics(base_deq)
rows.append(("BASE (full-slice)", "—", bt, bdd, bcal, 1.0))
for v in VARIANTS + EXTRA:
    tag = v if v.startswith("is_") else f"is_{v}"
    deq, diag = dp_mtm.reconstruct_window(os.path.join(RES, f"R3_{tag}.zip"),
                                          IS_S, IS_E)
    t, dd, cal = metrics(deq)
    rows.append((v, diag["n_trades"], t, dd, cal, t / bt))

print(f"{'variant':22s} {'trades':>6s} {'total%':>10s} {'maxDD%':>8s} {'Calmar':>8s} {'retention':>9s}")
for name, n, t, dd, cal, ret in sorted(rows, key=lambda r: -r[4]):
    print(f"{name:22s} {str(n):>6s} {t*100:10.2f} {dd*100:8.2f} {cal:8.2f} {ret:9.3f}")
