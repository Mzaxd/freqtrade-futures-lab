# hptB_plateau.py — parameter-plateau analysis for Hyperopt-B .fthypt results.
# Reads freqtrade's .fthypt JSON-lines result file, aggregates the parameter
# distribution of the top-20% epochs (by loss) vs all epochs, and prints the
# REGIME_SMA x PER_COIN_SMA joint distribution (the regime-switch pair most
# sensitive to cycle position; a lone spike = overfit).
# Usage: python hptB_plateau.py <file.fthypt> [top_frac=0.2]
import json
import sys
from collections import Counter, defaultdict

import numpy as np

PARAM_ORDER = ["regime_sma", "per_coin_sma", "regime_tolerance",
               "funding_max_p", "max_position_weight"]


def load(path: str):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            # fthypt v2: flat 'params_dict' holds every optimized parameter.
            params = dict(d.get("params_dict", {}))
            if not params:
                for sp in ("buy", "sell"):
                    params.update(d.get("params", {}).get(sp, {}))
            rm = d.get("results_metrics", {})
            rows.append(dict(
                epoch=d.get("current_epoch"),
                loss=d.get("loss"),
                params=params,
                trades=rm.get("total_trades"),
                profit=rm.get("profit_total"),
                maxdd=rm.get("max_drawdown_account"),
            ))
    return rows


def main(path: str, top_frac: float) -> None:
    rows = [r for r in load(path) if r["loss"] is not None
            and np.isfinite(r["loss"]) and r["loss"] < 100]
    rows.sort(key=lambda r: r["loss"])
    n = len(rows)
    k = max(1, int(round(n * top_frac)))
    top = rows[:k]
    print(f"{path}: {n} finite-loss epochs; top {k} ({top_frac:.0%}) analyzed")
    print(f"loss range: best={rows[0]['loss']:.5f} "
          f"median={rows[n//2]['loss']:.5f} worst={rows[-1]['loss']:.5f}")

    names = [p for p in PARAM_ORDER if p in rows[0]["params"]]
    for p in names:
        c_all = Counter(r["params"][p] for r in rows)
        c_top = Counter(r["params"][p] for r in top)
        print(f"\n-- {p} --")
        for v in sorted(c_all, key=lambda x: str(x)):
            fa = c_all[v] / n * 100
            ft = c_top.get(v, 0) / k * 100
            print(f"  {str(v):>8}: all {fa:5.1f}%   top {ft:5.1f}%")

    # joint REGIME_SMA x PER_COIN_SMA among top
    if {"regime_sma", "per_coin_sma"} <= set(names):
        joint = Counter((r["params"]["regime_sma"], r["params"]["per_coin_sma"]) for r in top)
        loss_cell = defaultdict(list)
        for r in rows:
            loss_cell[(r["params"]["regime_sma"], r["params"]["per_coin_sma"])].append(r["loss"])
        smas = sorted({k_[0] for k_ in joint})
        pcsv = sorted({k_[1] for k_ in joint})
        print("\n-- joint REGIME_SMA x PER_COIN_SMA (top set counts / all-epoch mean loss) --")
        head = "          " + "".join(f"{p:>16}" for p in pcsv)
        print(head)
        for s in smas:
            cells = []
            for p in pcsv:
                cnt = joint.get((s, p), 0)
                ml = np.mean(loss_cell[(s, p)]) if loss_cell.get((s, p)) else float("nan")
                cells.append(f"{cnt:>6}/{ml:8.3f}" if np.isfinite(ml) else f"{cnt:>6}/   -  ")
            print(f"  SMA{s:>4} " + "".join(f"{c:>16}" for c in cells))

    # best 10 rows detail
    print("\n-- best 10 epochs --")
    for r in rows[:10]:
        ps = " ".join(f"{p.split('_')[0][:5]}={r['params'][p]}" for p in names)
        print(f"  ep{r['epoch']:>4} loss={r['loss']:.5f} trades={r['trades']} "
              f"profit={r['profit']*100 if r['profit'] is not None else float('nan'):9.1f}% "
              f"maxDD={r['maxdd']*100 if r['maxdd'] is not None else float('nan'):5.1f}%  {ps}")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.2)
