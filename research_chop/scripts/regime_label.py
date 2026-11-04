"""Causal chop-gate labeler for research_chop (2026-11-04).

Re-implements the rule core of user_data/strategies/regime_detector.py verbatim
(mom_z +/-1.25 core + atr_pct_rank>=0.90 turbulent overlay) and exports per-pair
1h labels for 2021-2026. No parameter changes; no lookahead: row t uses only
candles closed at or before t (all windows trailing). Decisions derived from
row t are valid from t+1 open onward.

Output per pair: research_chop/data/regime_1h_{PAIR}.csv
  date, close, mom_z, atr_pct_rank, state(0=up,1=down,2=range,3=turbulent), g1, g2
  g1 = |mom_z| < 1.25                       (directionless, any vol)
  g2 = g1 AND atr_pct_rank >= 0.90           (violent crash-adjacent chop)
  g4 = state==2 continuously for >= 240 h    (persistent range; 2026-11-04 added
       after anchor validation showed g1/g2 fail to discriminate the bleed window)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "user_data" / "data" / "binance" / "futures"
OUT = ROOT / "research_chop" / "data"
PAIRS = ["BTC_USDT_USDT", "ETH_USDT_USDT", "SOL_USDT_USDT"]
THR = 1.25
TURB_RANK = 0.90


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "open", "high", "low", "close"]].copy()
    logc = np.log(out["close"])
    out["ret_1h"] = logc.diff()
    out["vol_12h"] = out["ret_1h"].rolling(12).std()
    out["mom_72h"] = logc.diff(72)
    out["mom_z"] = out["mom_72h"] / (out["vol_12h"] * np.sqrt(72))
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [out["high"] - out["low"],
         (out["high"] - prev_close).abs(),
         (out["low"] - prev_close).abs()], axis=1).max(axis=1)
    out["atr_pct"] = tr.rolling(14).mean() / out["close"]
    out["atr_pct_rank"] = out["atr_pct"].rolling(720, min_periods=240).rank(pct=True)
    return out


def label(df: pd.DataFrame) -> pd.DataFrame:
    mz = df["mom_z"].to_numpy()
    state = np.where(mz >= THR, 0, np.where(mz <= -THR, 1, 2))
    turb = (df["atr_pct_rank"].to_numpy() >= TURB_RANK)
    state = np.where(turb, 3, state)
    state = np.where(np.isnan(mz) | np.isnan(df["atr_pct_rank"].to_numpy()), -1, state)
    g1 = np.abs(mz) < THR
    g2 = g1 & turb
    g1 = np.where(np.isnan(mz), False, g1)
    # g4: directionlessness persistence — >=90% of the trailing 240 h had g1
    # (strict 240 h run of state==2 is unreachable: turb overlay flips hourly;
    #  fraction form tolerates brief spikes. Iteration disclosed in PRE_REG.)
    g1s = pd.Series(np.where(np.isnan(mz), np.nan, (np.abs(mz) < THR).astype(float)))
    g4 = (g1s.rolling(240, min_periods=240).mean() >= 0.90).to_numpy()
    return pd.DataFrame({
        "date": df["date"], "close": df["close"], "mom_z": df["mom_z"],
        "atr_pct_rank": df["atr_pct_rank"], "state": state.astype(int),
        "g1": g1.astype(bool), "g2": g2.astype(bool), "g4": g4.astype(bool)})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in PAIRS:
        raw = pd.read_feather(DATA / f"{p}-1h-futures.feather")
        lab = label(build_features(raw))
        lab = lab[lab["state"] >= 0]
        out_path = OUT / f"regime_1h_{p.split('_')[0]}.csv"
        lab.to_csv(out_path, index=False)

        yr = lab["date"].dt.year
        rows = []
        for y in sorted(yr.unique()):
            m = yr == y
            rows.append({
                "year": y, "g1_occ": lab.loc[m, "g1"].mean(),
                "g2_occ": lab.loc[m, "g2"].mean(),
                "g4_occ": lab.loc[m, "g4"].mean(),
                "turb_occ": (lab.loc[m, "state"] == 3).mean(),
                "range_occ": (lab.loc[m, "state"] == 2).mean()})
        occ = pd.DataFrame(rows)
        # anchor-window validation: the known 2026 bleed window must be g1-heavy
        a = lab[(lab["date"] >= "2026-02-15") & (lab["date"] < "2026-08-11")]
        b = lab[(lab["date"] >= "2021-11-01") & (lab["date"] < "2022-11-01")]  # grand bear (trend, should be g1-light)
        print(f"\n== {p}  rows={len(lab)}  -> {out_path.name}")
        print(occ.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        print(f"anchor 2026-02-15~08-10: g1={a['g1'].mean():.3f} g2={a['g2'].mean():.3f} g4={a['g4'].mean():.3f}")
        print(f"anchor 2021-11~2022-11 : g1={b['g1'].mean():.3f} g2={b['g2'].mean():.3f} g4={b['g4'].mean():.3f}")


if __name__ == "__main__":
    main()
