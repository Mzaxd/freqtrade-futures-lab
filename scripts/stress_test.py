#!/usr/bin/env python
"""Stress-test suite for a strategy: parameter perturbation, delayed entry,
random trade skipping, fee uplift, per-pair and per-segment robustness.

Generates temporary strategy subclasses (deterministic, seeded), runs backtests
on a given timerange, and writes a combined stress report.

Usage:
  python scripts/stress_test.py STRATEGY TIMERANGE TAG

Outputs: user_data/reports/summary_stress_{TAG}.csv / .md
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRAT_DIR = ROOT / "user_data/strategies"

PARAMS = {  # strategy -> (base class, key params and their perturbations)
    "TrendBaselineV1": {
        "base": "TrendBaselineV1",
        "params": {
            "adx_min": ("IntParameter(15, 30, default={}, space='buy')", 20),
            "atr_stop_mult": ("DecimalParameter(2.0, 4.0, default={}, decimals=1, space='sell')", 3.0),
            "atr_trail_mult": ("DecimalParameter(1.0, 3.0, default={}, decimals=1, space='sell')", 1.5),
        },
    },
    "TrendVolFundingV3": {
        "base": "TrendVolFundingV3",
        "params": {
            "adx_min": ("IntParameter(15, 30, default={}, space='buy')", 20),
            "atr_stop_mult": ("DecimalParameter(2.0, 4.0, default={}, decimals=1, space='sell')", 3.0),
            "atr_trail_mult": ("DecimalParameter(1.0, 3.0, default={}, decimals=1, space='sell')", 1.5),
            "vol_pct_min": ("DecimalParameter(0.05, 0.35, default={}, decimals=2, space='buy')", 0.20),
            "vol_pct_max": ("DecimalParameter(0.70, 0.98, default={}, decimals=2, space='buy')", 0.92),
            "funding_max_abs": ("DecimalParameter(0.0001, 0.0006, default={}, decimals=4, space='buy')", 0.0003),
        },
    },
    "DonchianBreakoutV2": {
        "base": "DonchianBreakoutV2",
        "params": {
            "entry_lookback": ("IntParameter(48, 168, default={}, space='buy')", 96),
            "exit_lookback": ("IntParameter(24, 72, default={}, space='sell')", 48),
            "adx_min": ("IntParameter(15, 25, default={}, space='buy')", 18),
            "atr_stop_mult": ("DecimalParameter(2.0, 4.0, default={}, decimals=1, space='sell')", 3.0),
        },
    },
}

DELAY_TMPL = '''
from pandas import DataFrame
from {base} import {base} as _Base


class {cls}(_Base):
    """Entry delayed by {n} candle(s) (stress: latency)."""

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Base.populate_entry_trend(self, dataframe, metadata)
        for col in ("enter_long", "enter_short"):
            if col in dataframe.columns:
                dataframe[col] = dataframe[col].shift({n}).fillna(0.0)
        return dataframe
'''

SKIP_TMPL = '''
import numpy as np
from pandas import DataFrame
from {base} import {base} as _Base


class {cls}(_Base):
    """Randomly skip {pct}% of entry signals (stress: missed fills). Seed fixed."""

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = _Base.populate_entry_trend(self, dataframe, metadata)
        rng = np.random.default_rng({seed})
        mask = rng.random(len(dataframe)) < {frac}
        for col in ("enter_long", "enter_short"):
            if col in dataframe.columns:
                dataframe.loc[mask, col] = 0.0
        return dataframe
'''

PERTURB_TMPL = '''
from {base} import {base} as _Base
from freqtrade.strategy import IntParameter, DecimalParameter


class {cls}(_Base):
    """Perturbed: {desc}"""

{param_lines}
'''


def clamp_int(v, lo, hi):
    return max(lo, min(hi, int(round(v))))


def clamp_dec(v, lo, hi):
    return max(lo, min(hi, round(v, 6)))


def build_variants(strategy: str) -> dict[str, str]:
    """Return {class_name: file_content} for all stress variants."""
    spec = PARAMS[strategy]
    base = spec["base"]
    variants: dict[str, str] = {}

    for pname, (tmpl, default) in spec["params"].items():
        is_int = tmpl.startswith("IntParameter")
        for pct in (-0.20, -0.10, 0.10, 0.20):
            newv = default * (1 + pct)
            if is_int:
                lo, hi = (int(s) for s in tmpl.split("(")[1].split(")")[0].split(",")[:2])
                newv = clamp_int(newv, lo, hi)
                # ensure a real change; if rounding removed it, step by 1 in direction
                if newv == default:
                    newv = clamp_int(default + (1 if pct > 0 else -1), lo, hi)
            else:
                lo, hi = (float(s) for s in tmpl.split("(")[1].split(")")[0].split(",")[:2])
                newv = clamp_dec(newv, lo, hi)
            tag = f"{pname}_{'p' if pct > 0 else 'm'}{abs(pct):.0%}".replace("%", "").replace(".", "p")
            cls = f"Stress_{strategy}_{tag}"
            line = f"    {pname} = {tmpl.format(newv)}"
            variants[cls] = PERTURB_TMPL.format(
                base=base, cls=cls, desc=f"{pname}: {default} -> {newv} ({pct:+.0%})",
                param_lines=line,
            )

    # joint +10% on all params
    lines = []
    for pname, (tmpl, default) in spec["params"].items():
        is_int = tmpl.startswith("IntParameter")
        lo, hi = (int(s) for s in tmpl.split("(")[1].split(")")[0].split(",")[:2]) if is_int else \
                 (float(s) for s in tmpl.split("(")[1].split(")")[0].split(",")[:2])
        newv = clamp_int(default * 1.1, lo, hi) if is_int else clamp_dec(default * 1.1, lo, hi)
        lines.append(f"    {pname} = {tmpl.format(newv)}")
    variants[f"Stress_{strategy}_joint_p10"] = PERTURB_TMPL.format(
        base=base, cls=f"Stress_{strategy}_joint_p10", desc="all params +10%", param_lines="\n".join(lines))

    variants[f"Stress_{strategy}_delay1"] = DELAY_TMPL.format(base=base, cls=f"Stress_{strategy}_delay1", n=1)
    variants[f"Stress_{strategy}_delay2"] = DELAY_TMPL.format(base=base, cls=f"Stress_{strategy}_delay2", n=2)
    for pct in (10, 20):
        cls = f"Stress_{strategy}_skip{pct}"
        variants[cls] = SKIP_TMPL.format(base=base, cls=cls, pct=pct, frac=pct / 100, seed=42)

    return variants


def run(strategy: str, timerange: str, tag: str, extra_backtest_args: list[str] | None = None):
    variants = build_variants(strategy)
    zips = []
    for cls, content in variants.items():
        f = STRAT_DIR / f"_{cls}.py"
        f.write_text(content)
        try:
            r = subprocess.run(
                ["bash", "scripts/run_backtest.sh", cls, timerange, f"stress_{tag}"]
                + (extra_backtest_args or []),
                cwd=ROOT, capture_output=True, text=True, timeout=1200,
            )
            z = ROOT / f"user_data/backtest_results/stress_{tag}_{cls}.zip"
            if z.exists():
                zips.append(str(z))
                print(f"[ok] {cls}")
            else:
                print(f"[FAIL] {cls}\n{r.stdout[-1500:]}\n{r.stderr[-800:]}")
        finally:
            f.unlink(missing_ok=True)
    if zips:
        subprocess.run([".venv/bin/python", "scripts/summarize_results.py", f"stress_{tag}"] + zips,
                       cwd=ROOT, check=True)


if __name__ == "__main__":
    strategy, timerange, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    extra = sys.argv[4:] or None
    run(strategy, timerange, tag, extra)
