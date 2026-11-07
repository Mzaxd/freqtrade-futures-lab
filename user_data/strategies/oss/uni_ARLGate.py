"""uni_ARLGate — point-in-time universe gating for sleeve A (research_improve/uni).

Hypothesis under test (uni line): the frozen universe (coins listed before
2021-12-31) structurally excludes the 2022+ listing wave; A (ARL_2x =
OPT9_Recycle RECYCLE_MULT=1.21, lev 2x) is a volatility-event harvester and
newly listed high-volatility coins still carry 2021-amplitude moves, so a
point-in-time (vol/liquidity) admission rule can restore A's raw material.

Mechanics — BYTE-IDENTICAL to ARL_2x except ONE overlay: after the frozen
entry logic (OPT4 atr08-gated ATR breakout), `enter_long`/`enter_short` are
zeroed for (pair, month) combinations NOT in the pre-built universe snapshot
CSV. Exits are NEVER gated (reverse-signal / ATR-stop / time-stop continue to
manage in-flight positions after a coin leaves the universe — no forced
liquidation on removal; pre-registered in research_improve/uni/pre_reg.md).

Universe CSV format (one row per ACTIVE month):
    pair,month
    RAYSOL/USDT:USDT,2025-02
Month M membership is computed OFFLINE from daily bars STRICTLY BEFORE month
M (causal, executable ex-ante) — see research_improve/uni/build_universe.py.

Three arms (pre-registered):
  uni_ARL_frozen12 — no CSV (UNIVERSE_CSV=None): regression-identity arm,
                     must trade like plain ARL_2x on the frozen 12.
  uni_ARL_ext      — universe_ext.csv: NEW coins (2022+ listings) gated by
                     the PIT rule; pairs ABSENT from the CSV are always
                     tradeable (the frozen 12 stay permanent members).
  uni_ARL_pit      — universe_pit.csv: ALL coins (incl. frozen 12) must pass
                     the same PIT rule each month; a pair absent from the
                     CSV never trades. BTC/USDT:USDT stays in the backtest
                     whitelist regardless (recycle reference data), it just
                     may stop generating entries in low-RV months.
"""
from pathlib import Path

import pandas as pd
from pandas import DataFrame

from AB_LevGrid import ARL_2x

_REPO_ROOT = Path(__file__).resolve().parents[3]
_UNI_DIR = _REPO_ROOT / "research_improve" / "uni"


class UniARLGateBase(ARL_2x):
    UNIVERSE_CSV = None          # None -> no gating (identity arm)
    GATE_ABSENT_PAIRS = False    # True: pairs missing from CSV never trade

    _universe_cache: dict | None = None   # pair -> set of "YYYY-MM"

    def _universe(self) -> dict:
        if self._universe_cache is None:
            cache: dict = {}
            if self.UNIVERSE_CSV is not None:
                path = Path(self.UNIVERSE_CSV)
                if not path.is_absolute():
                    path = _UNI_DIR / path
                csv = pd.read_csv(path)
                for pair, month in zip(csv["pair"], csv["month"]):
                    cache.setdefault(str(pair), set()).add(str(month))
            self.__class__._universe_cache = cache
        return self._universe_cache

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_entry_trend(dataframe, metadata)
        uni = self._universe()
        if not uni:
            return df
        pair = metadata["pair"]
        months = uni.get(pair)
        if months is None:
            if self.GATE_ABSENT_PAIRS:
                df["enter_long"] = 0
                df["enter_short"] = 0
            return df  # absent + permissive -> always tradeable
        ym = df["date"].dt.strftime("%Y-%m")
        keep = ym.isin(months)
        df.loc[~keep, "enter_long"] = 0
        df.loc[~keep, "enter_short"] = 0
        return df


class uni_ARL_frozen12(UniARLGateBase):
    """Arm (a): frozen 12-coin baseline, no gating."""
    UNIVERSE_CSV = None


class uni_ARL_ext(UniARLGateBase):
    """Arm (b): frozen 12 + PIT-admitted new listings."""
    UNIVERSE_CSV = "universe_ext.csv"
    GATE_ABSENT_PAIRS = False


class uni_ARL_pit(UniARLGateBase):
    """Arm (c): pure point-in-time rule universe (all coins gated)."""
    UNIVERSE_CSV = "universe_pit.csv"
    GATE_ABSENT_PAIRS = True
