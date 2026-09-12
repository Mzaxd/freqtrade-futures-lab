# OPT7 (S5): export causal rule-based regime series for ALL 23 lab pairs.
#
# Reuses regime_detector.py's FROZEN rule pipeline verbatim (rule_states with
# THR=1.25 + turbulent ATR%-rank overlay + dwell_smooth k=2) - no refit, no new
# parameters; the rule core is pair-local and causal, so applying it to pairs
# beyond the original BTC/ETH/SOL export set is a legitimate universe transfer.
#
# Output: user_data/regimes_opt7/{PAIR}_regime.csv, rows filtered to
# date < 2024-01-01 (S5 data discipline: the 2024-26 window is banned for the
# Router line). BTC/ETH/SOL regenerated rows are validated against the original
# user_data/regimes CSVs on the overlap - proves provenance (rules, not HMM)
# and pipeline determinism.
from __future__ import annotations

import os
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "user_data" / "strategies"))

import regime_detector as rd  # noqa: E402

CUTOFF = "2024-01-01"
OLD12 = ["BTC_USDT_USDT", "ETH_USDT_USDT", "SOL_USDT_USDT", "BNB_USDT_USDT",
         "XRP_USDT_USDT", "ADA_USDT_USDT", "DOGE_USDT_USDT", "AVAX_USDT_USDT",
         "LINK_USDT_USDT", "DOT_USDT_USDT", "LTC_USDT_USDT", "UNI_USDT_USDT"]
NEW11 = ["AAVE_USDT_USDT", "ATOM_USDT_USDT", "BCH_USDT_USDT", "ETC_USDT_USDT",
         "FIL_USDT_USDT", "IOTA_USDT_USDT", "NEAR_USDT_USDT", "THETA_USDT_USDT",
         "TRX_USDT_USDT", "VET_USDT_USDT", "XLM_USDT_USDT"]
OUT = LAB / "user_data" / "regimes_opt7"
ORIG = LAB / "user_data" / "regimes"


def main() -> None:
    assert os.environ.get("FTLAB_REGIME_THR") is None, \
        "refusing to export with a perturbed threshold"
    q = rd._train_label_quantiles()
    OUT.mkdir(parents=True, exist_ok=True)
    for pair in OLD12 + NEW11:
        f = rd.build_features(rd.load_pair_1h(pair))
        st = rd.get_states(f, q, rules=True, art=None)
        st = st[st["date"] < rd.pd.Timestamp(CUTOFF, tz="UTC")]
        st.to_csv(OUT / f"{pair}_regime.csv", index=False)
        valid = (st["regime"] >= 0).mean()
        dist = st["regime"].value_counts(normalize=True).round(3).to_dict()
        print(f"exported {pair}: {len(st)} rows (<{CUTOFF}), "
              f"valid={valid:.3f}, dist={dist}", flush=True)

    # provenance check vs the original 3-pair export (overlap 2021-2023)
    print("\n--- validation vs original user_data/regimes CSVs ---")
    ok_all = True
    for pair in ["BTC_USDT_USDT", "ETH_USDT_USDT", "SOL_USDT_USDT"]:
        a = rd.pd.read_csv(ORIG / f"{pair}_regime.csv", parse_dates=["date"])
        b = rd.pd.read_csv(OUT / f"{pair}_regime.csv", parse_dates=["date"])
        a = a[(a["date"] >= "2021-01-01") & (a["date"] < "2024-01-01")]
        m = a.merge(b, on="date", suffixes=("_o", "_n"), how="inner")
        reg_match = (m["regime_o"] == m["regime_n"]).mean()
        conf_gap = (m["conf_o"] - m["conf_n"]).abs().max()
        ok = reg_match == 1.0 and conf_gap < 1e-9
        ok_all &= ok
        print(f"{pair}: rows={len(m)} regime_match={reg_match:.6f} "
              f"max_conf_gap={conf_gap:.2e} -> {'OK' if ok else 'MISMATCH'}")
    print("PROVENANCE:", "rules-pipeline CONFIRMED" if ok_all else "MISMATCH - investigate")


if __name__ == "__main__":
    main()
