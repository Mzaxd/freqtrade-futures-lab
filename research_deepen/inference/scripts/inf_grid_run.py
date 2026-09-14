"""inf_grid_run.py — orchestrate the 75-config CSCV/PBO backtest grid.

Usage (from repo root):
    .venv/bin/python research_deepen/inference/scripts/inf_grid_run.py [--jobs 4]

- Runs `freqtrade backtesting` per grid cell (module-scope type() factory
  classes from research_deepen/inference/strategies/INF_grid.py), timerange
  20210101-20240101, 12-coin pool, fee 0.0005 (OPT7_config_12p.json).
- Max 4 concurrent subprocesses (CHARTER hard cap).
- Zip hygiene: after each run, the newest backtest-result-*.zip whose embedded
  strategy name equals the class AND whose mtime is newer than the run start is
  renamed into research_deepen/inference/results/grid/<tag>.zip (its .meta.json
  companion is moved along). Idempotent: existing <tag>.zip is verified and
  skipped.
- Writes an incremental summary CSV results/grid/grid_summary.csv.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GRID_DIR = os.path.join(REPO, "research_deepen", "inference", "results", "grid")
BT_DIR = os.path.join(REPO, "user_data", "backtest_results")
LOG_DIR = os.path.join(REPO, "research_deepen", "inference", "results", "logs")

SIGNAL_GRID = [1.6, 1.8, 2.0, 2.2, 2.4]
STOP_GRID = [1.6, 1.8, 2.0, 2.2, 2.4]
RESAMPLE_GRID = [2, 3, 4]
TIMERANGE = "20210101-20240101"


def cell_names():
    out = []
    for sig in SIGNAL_GRID:
        for stop in STOP_GRID:
            for rh in RESAMPLE_GRID:
                tag = f"s{int(round(sig * 10)):02d}_t{int(round(stop * 10)):02d}_r{rh}"
                out.append((tag, f"INF_G_{tag}", sig, stop, rh))
    return out


def read_zip_metrics(path: str) -> dict | None:
    """Return {'strategy': name, 'profit_total': .., 'sharpe': .., ...} or None."""
    try:
        with zipfile.ZipFile(path) as z:
            jname = [
                n
                for n in z.namelist()
                if n.endswith(".json") and "config" not in n and "market" not in n
            ][0]
            data = json.loads(z.read(jname))
    except Exception:
        return None
    if len(data.get("strategy", {})) != 1:
        return None
    name, st = next(iter(data["strategy"].items()))
    return {
        "strategy": name,
        "trades": st["total_trades"],
        "profit_total_pct": round(st["profit_total"] * 100, 2),
        "maxdd_pct": round(st["max_drawdown_account"] * 100, 2),
        "sharpe": round(st.get("sharpe") or 0.0, 4),
        "profit_factor": round(st.get("profit_factor") or 0.0, 4),
        "start": st["backtest_start"][:10],
        "end": st["backtest_end"][:10],
    }


def find_and_archive(strategy: str, run_started_ts: float, tag: str) -> str | None:
    """Newest backtest-result-*.zip with embedded strategy == strategy and
    mtime >= run_started_ts -> move to GRID_DIR/<tag>.zip."""
    cands = sorted(
        glob.glob(os.path.join(BT_DIR, "backtest-result-*.zip")),
        key=os.path.getmtime,
        reverse=True,
    )
    for f in cands[:60]:
        if os.path.getmtime(f) < run_started_ts:
            continue
        m = read_zip_metrics(f)
        if m and m["strategy"] == strategy:
            dest = os.path.join(GRID_DIR, f"{tag}.zip")
            if os.path.exists(dest):
                os.remove(dest)
            os.rename(f, dest)
            # move the .meta.json companion if present
            base = os.path.basename(f)[: -len(".zip")]
            for meta in glob.glob(os.path.join(BT_DIR, base + ".json.meta.json")):
                os.rename(meta, os.path.join(GRID_DIR, f"{tag}.meta.json"))
            return dest
    return None


def run_cell(job, force: bool) -> dict:
    tag, cls, sig, stop, rh = job
    dest = os.path.join(GRID_DIR, f"{tag}.zip")
    if not force and os.path.exists(dest):
        m = read_zip_metrics(dest)
        if m and m["strategy"] == cls and m["start"] == "2021-01-01":
            return {"tag": tag, "status": "reused", **m}
    safe_tag = str(tag).replace("/", "_").replace("\\", "_").replace("..", "_")
    log_path = os.path.join(LOG_DIR, f"grid_{safe_tag}.log")
    cmd = [
        sys.executable,
        "-m",
        "freqtrade",
        "backtesting",
        "--userdir",
        "user_data",
        "--config",
        "user_data/configs/OPT7_config_12p.json",
        "--strategy-path",
        "research_deepen/inference/strategies/grid",
        "--strategy",
        cls,
        "--timerange",
        TIMERANGE,
        "--export",
        "trades",
        "--cache",
        "none",
    ]
    t0 = time.time()
    time.sleep(3.0)  # stagger to reduce same-second zip filename collisions
    started_ts = time.time() - 2.0
    with Path(log_path).open("w") as logf:
        rc = subprocess.run(cmd, cwd=REPO, stdout=logf, stderr=subprocess.STDOUT).returncode
    elapsed = round(time.time() - t0, 1)
    if rc != 0:
        return {"tag": tag, "status": f"FAILED rc={rc}", "elapsed_s": elapsed}
    z = find_and_archive(cls, started_ts, tag)
    if z is None:
        return {"tag": tag, "status": "NO_ZIP", "elapsed_s": elapsed}
    m = read_zip_metrics(z)
    if m is None:
        return {"tag": tag, "status": "UNREADABLE_ZIP", "elapsed_s": elapsed}
    return {"tag": tag, "status": "ok", "elapsed_s": elapsed, **m}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", type=str, default=None, help="comma-separated tags")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    jobs = cell_names()
    if args.only:
        keep = set(args.only.split(","))
        jobs = [j for j in jobs if j[0] in keep]

    os.makedirs(GRID_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    summary_path = os.path.join(GRID_DIR, "grid_summary.csv")
    fields = [
        "tag", "status", "elapsed_s", "strategy", "trades", "profit_total_pct",
        "maxdd_pct", "sharpe", "profit_factor", "start", "end",
        "signal_atr_mult", "stop_atr_mult", "resample_hours",
    ]
    done_rows: dict[str, dict] = {}
    if os.path.exists(summary_path):
        with open(summary_path, newline="") as f:
            for row in csv.DictReader(f):
                done_rows[row["tag"]] = row

    print(f"[inf_grid_run] {len(jobs)} cells, jobs={args.jobs}", flush=True)
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futmap = {ex.submit(run_cell, j, args.force): j for j in jobs}
        n = 0
        for fut in cf.as_completed(futmap):
            j = futmap[fut]
            try:
                row = fut.result()
            except Exception as e:  # noqa: BLE001
                row = {"tag": j[0], "status": f"EXC {type(e).__name__}: {e}"}
            row["signal_atr_mult"] = j[2]
            row["stop_atr_mult"] = j[3]
            row["resample_hours"] = j[4]
            done_rows[row["tag"]] = {k: row.get(k, "") for k in fields}
            n += 1
            print(
                f"[{n}/{len(jobs)}] {row['tag']} -> {row.get('status')} "
                f"(profit {row.get('profit_total_pct')}%, dd {row.get('maxdd_pct')}%, "
                f"sharpe {row.get('sharpe')}, {row.get('elapsed_s', '')}s)",
                flush=True,
            )
            with Path(summary_path).open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for t in sorted(done_rows):
                    w.writerow(done_rows[t])
    print(f"[inf_grid_run] all done in {round(time.time() - t0)}s", flush=True)


if __name__ == "__main__":
    main()
