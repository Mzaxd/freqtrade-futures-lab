#!/usr/bin/env python
"""Generate perturbed/delayed variants of RegimeRouter and run them.

Covers 6.2 stress items: parameter +/-10% perturbation (ATR stop, ATR trail,
range risk multiplier, detector threshold) and 1-bar entry delay.
Writes variant strategy files (prefixed _Stress), runs each, cleans up.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRAT = ROOT / "user_data/strategies"

PERTURB = """
from regime_router import RegimeRouter as _Base


class {cls}(_Base):
    \"\"\"{desc}\"\"\"
{lines}
"""

DELAY = """
from pandas import DataFrame
from regime_router import RegimeRouter as _Base


class {cls}(_Base):
    \"\"\"Entry delayed by 1 candle (stress: latency).\"\"\"

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Base.populate_entry_trend(self, dataframe, metadata)
        for col in ("enter_long", "enter_short"):
            if col in dataframe.columns:
                dataframe[col] = dataframe[col].shift(1).fillna(0.0)
        return dataframe
"""

VARIANTS = {
    "StressR_stop_lo": "    TL_ATR_STOP = 2.7\n    TS_ATR_STOP = 2.7\n    MR_ATR_STOP = 1.8",
    "StressR_stop_hi": "    TL_ATR_STOP = 3.3\n    TS_ATR_STOP = 3.3\n    MR_ATR_STOP = 2.2",
    "StressR_trail_lo": "    TL_ATR_TRAIL = 3.8\n    TS_ATR_TRAIL = 3.8",
    "StressR_trail_hi": "    TL_ATR_TRAIL = 4.6\n    TS_ATR_TRAIL = 4.6",
    "StressR_rrm_lo": "    RANGE_RISK_MULT = 0.45",
    "StressR_rrm_hi": "    RANGE_RISK_MULT = 0.55",
}


def run(cls: str, timerange: str, tag: str, env_extra: dict | None = None) -> bool:
    env = dict(os.environ)
    env.update(env_extra or {})
    r = subprocess.run(["bash", "scripts/run_backtest.sh", cls, timerange, tag],
                       cwd=ROOT, capture_output=True, text=True, env=env, timeout=1800)
    ok = (ROOT / f"user_data/backtest_results/{tag}_{cls}.zip").exists()
    print(("[ok] " if ok else "[FAIL] ") + cls)
    return ok


def main():
    timerange = sys.argv[1] if len(sys.argv) > 1 else "20210101-20250101"
    zips = []

    # detector threshold +/-10%: export perturbed regime series to alt dirs
    for name, thr in (("thr_lo", "1.125"), ("thr_hi", "1.375")):
        outdir = ROOT / f"user_data/regimes_{name}"
        env = dict(os.environ, FTLAB_REGIME_THR=thr)
        subprocess.run([".venv/bin/python", "user_data/strategies/regime_detector.py",
                        "export", "--rules", "--start", "2020-01-01",
                        "--out", str(outdir)], cwd=ROOT, env=env, check=True,
                       capture_output=True)
        ok = run("RegimeRouter", timerange, f"st_{name}",
                 {"FTLAB_REGIME_DIR": str(outdir)})
        if ok:
            zips.append(str(ROOT / f"user_data/backtest_results/st_{name}_RegimeRouter.zip"))

    # router param perturbations
    for cls, lines in VARIANTS.items():
        f = STRAT / f"_{cls}.py"
        f.write_text(PERTURB.format(cls=cls, desc=f"perturbed: {lines}", lines=lines))
        try:
            if run(cls, timerange, "st", None):
                zips.append(str(ROOT / f"user_data/backtest_results/st_{cls}.zip"))
        finally:
            f.unlink(missing_ok=True)

    # delay 1 bar
    cls = "StressR_delay1"
    f = STRAT / f"_{cls}.py"
    f.write_text(DELAY.format(cls=cls))
    try:
        if run(cls, timerange, "st", None):
            zips.append(str(ROOT / f"user_data/backtest_results/st_{cls}.zip"))
    finally:
        f.unlink(missing_ok=True)

    print("ZIPS:", *zips, sep="\n  ")


if __name__ == "__main__":
    main()
