"""WS-C0 deliverable 2: A-sleeve bleed attribution to gate ON/OFF days.

Daily attribution convention (disclosed in report):
- Hourly gate label at row t uses only <=t data; the state is *active* for the
  return of candle (t, t+1], so labels are shift(1)-aligned before daily
  aggregation (no same-hour lookahead).
- Day d counts h ON-hours (of 24). MAIN convention: ON day iff h >= 12 (>=50%).
  Sensitivity: ON day iff h >= 1.
- Daily MTM stamps (dp_mtm) are end-of-day marks => r_d = eq_d/eq_{d-1}-1 is the
  return accrued *during* calendar day d, matched against day d's gate labels.

Anchors: 2026-02-15..2026-08-10 bleed, 2025-10-01..2026-06-30 downtrend,
2021-11-01..2022-11-01 grand bear.

Outputs (research_chop/logs/):
  ws_c0_attr_regime_stats.csv      ON/OFF split per sleeve x coin x gate x rule
  ws_c0_attr_capture.csv           losing-day capture rates
  ws_c0_attr_anchors.csv           anchor-window ON share & segmented returns
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research_chop" / "data"
LOGS = ROOT / "research_chop" / "logs"
COINS = ["BTC", "ETH", "SOL"]
GATES = ["g1", "g2", "g4"]
SLEEVES = {"A3": "mtm_daily_A3.csv", "B3": "mtm_daily_B3.csv"}
ANCHORS = {
    "bleed_2026": ("2026-02-15", "2026-08-10"),
    "downtrend_2025-26": ("2025-10-01", "2026-06-30"),
    "bear_2021-22": ("2021-11-01", "2022-11-01"),
}


def load_mtm(name: str) -> pd.Series:
    df = pd.read_csv(ROOT / "user_data" / "logs" / name, index_col=0, parse_dates=True)
    eq = df.iloc[:, 0]
    ret = eq.pct_change().dropna()
    ret.index = ret.index.tz_localize(None)
    return ret


def daily_on_hours(coin: str, gate: str, shift: int) -> pd.Series:
    df = pd.read_csv(DATA / f"regime_1h_{coin}.csv", parse_dates=["date"]).set_index("date")
    on = df[gate].shift(shift).to_numpy(dtype=float)  # NaN -> not ON
    d = df.copy()
    d["on"] = np.nan_to_num(on, nan=0.0)
    day = d.index.tz_localize(None).normalize()
    return d.groupby(day)["on"].sum()


def stats_block(r: pd.Series, on_flag: pd.Series) -> dict:
    rr = r.values
    on = on_flag.values
    n = len(rr)
    out = {
        "n_days": n, "on_days": int(on.sum()), "off_days": int((~on).sum())}
    for tag, sel in (("ON", on), ("OFF", ~on)):
        x = pd.Series(rr[sel])
        if len(x) == 0:
            out[f"{tag}_ann_ret_pct"] = np.nan
            out[f"{tag}_ann_vol_pct"] = np.nan
            out[f"{tag}_sum_ret_pct"] = np.nan
            out[f"{tag}_worst30d_pct"] = np.nan
            continue
        out[f"{tag}_ann_ret_pct"] = round(100 * x.mean() * 365, 1)
        out[f"{tag}_ann_vol_pct"] = round(100 * x.std() * np.sqrt(365), 1)
        out[f"{tag}_sum_ret_pct"] = round(100 * x.sum(), 1)
        out[f"{tag}_worst30d_pct"] = (round(100 * x.rolling(30).sum().min(), 1)
                                       if len(x) >= 30 else np.nan)
    return out


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    rets = {k: load_mtm(v) for k, v in SLEEVES.items()}
    oh = {(c, g): daily_on_hours(c, g, 1) for c in COINS for g in GATES}
    oh_unshifted = {(c, g): daily_on_hours(c, g, 0) for c in COINS for g in GATES}

    # ---- regime split stats + capture ----
    rows, cap_rows = [], []
    for sleeve, r in rets.items():
        for coin in COINS:
            for gate in GATES:
                for rule, thr in (("main_ge12h", 12), ("sens_ge1h", 1)):
                    h = oh[(coin, gate)].reindex(r.index).fillna(0.0)
                    on_flag = h >= thr
                    row = {"sleeve": sleeve, "coin": coin, "gate": gate, "rule": rule}
                    row.update(stats_block(r, on_flag))
                    rows.append(row)
                    if rule == "main_ge12h":
                        lose = r < 0
                        cap_rows.append({
                            "sleeve": sleeve, "coin": coin, "gate": rule and gate,
                            "n_losing_days": int(lose.sum()),
                            "losing_days_on": int((lose & on_flag).sum()),
                            "capture_days_pct": round(100 * (lose & on_flag).sum() / max(lose.sum(), 1), 1),
                            "neg_mass_on_pct": round(100 * r[lose & on_flag].abs().sum()
                                                     / max(r[lose].abs().sum(), 1e-12), 1)})
    stats = pd.DataFrame(rows)
    stats.to_csv(LOGS / "ws_c0_attr_regime_stats.csv", index=False)
    cap = pd.DataFrame(cap_rows)
    cap.to_csv(LOGS / "ws_c0_attr_capture.csv", index=False)

    # ---- shift sensitivity on capture (unshifted labels, main threshold) ----
    sens_rows = []
    for sleeve, r in rets.items():
        for coin in COINS:
            for gate in GATES:
                h = oh_unshifted[(coin, gate)].reindex(r.index).fillna(0.0)
                on_flag = h >= 12
                lose = r < 0
                sens_rows.append({
                    "sleeve": sleeve, "coin": coin, "gate": gate, "rule": "unshifted_ge12h",
                    "n_losing_days": int(lose.sum()),
                    "losing_days_on": int((lose & on_flag).sum()),
                    "capture_days_pct": round(100 * (lose & on_flag).sum() / max(lose.sum(), 1), 1),
                    "neg_mass_on_pct": round(100 * r[lose & on_flag].abs().sum()
                                             / max(r[lose].abs().sum(), 1e-12), 1)})
    pd.concat([cap, pd.DataFrame(sens_rows)]).to_csv(LOGS / "ws_c0_attr_capture.csv", index=False)

    # ---- anchors ----
    arows = []
    for aname, (a0, a1) in ANCHORS.items():
        for sleeve, r in rets.items():
            rw = r.loc[a0:a1]
            for coin in COINS:
                for gate in GATES:
                    h = oh[(coin, gate)].reindex(rw.index).fillna(0.0)
                    on_flag = (h >= 12).values
                    arows.append({
                        "anchor": aname, "sleeve": sleeve, "coin": coin, "gate": gate,
                        "n_days": len(rw),
                        "on_share_pct": round(100 * on_flag.mean(), 1),
                        "ret_ON_sum_pct": round(100 * rw[on_flag].sum(), 1),
                        "ret_OFF_sum_pct": round(100 * rw[~on_flag].sum(), 1),
                        "ret_window_sum_pct": round(100 * rw.sum(), 1)})
    anch = pd.DataFrame(arows)
    anch.to_csv(LOGS / "ws_c0_attr_anchors.csv", index=False)

    pd.set_option("display.width", 250)
    print("== A3/B3 ON/OFF split (main: >=12 of 24 shifted ON-hours) ==")
    print(stats[stats["rule"] == "main_ge12h"].to_string(index=False))
    print("\n== losing-day capture (main rule; unshifted sensitivity appended) ==")
    print(pd.concat([cap, pd.DataFrame(sens_rows)]).to_string(index=False))
    print("\n== anchors ==")
    print(anch.to_string(index=False))
    print("\n== threshold sensitivity: ann ret ON/OFF, ge1h vs ge12h (A3) ==")
    a3 = stats[(stats.sleeve == "A3")]
    piv = a3.pivot_table(index=["coin", "gate"], columns="rule",
                         values=["ON_ann_ret_pct", "OFF_ann_ret_pct", "on_days"])
    print(piv.round(1).to_string())


if __name__ == "__main__":
    main()
