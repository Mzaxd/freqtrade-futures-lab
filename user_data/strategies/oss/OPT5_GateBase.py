# OPT5_GateBase — phase-5 door-1 scaffolding: OPT4 + a configurable SECOND
# anti-chop entry gate ("gate2"), declared set (phase5_charter.md):
#   er1h  : 1h Kaufman efficiency ratio ER(28) >= gate2_er_min
#   er3h  : 3h-resampled Kaufman ER(14) >= gate2_er_min
#   chop  : 1h Choppiness(14) <= gate2_chop_max
#   mlc   : 12h EMA(50) slope direction must agree with the entry side
#           (long needs rising, short needs falling)
#
# Design rules (phase-5 protocol):
#   * gate2 only ever REMOVES enter_long / enter_short entries; exits are never
#     touched (populate_exit_trend / custom_exit inherited unchanged from OPT4).
#   * Everything is computed from closed candles only — same availability
#     semantics as the vetted OPT1 resampled columns (resampled values land on
#     the 1h row at which the higher-timeframe candle completes; 1h rollings
#     use the just-closed row, acted on at the next row's open).
#   * NaN gate values block entries (fillna(False)), matching the atr08 gate.
#   * atr08 gate stays ON (inherited OPT4 entry trend) — every variant is the
#     atr08+gate2 stack by construction.
#   * MLC EMA uses min_periods=50 so the slope is only defined once 50 complete
#     12h candles exist (~25 days); early-2021 entries on pairs whose data
#     starts 2021-01-01 are correspondingly blocked (disclosed in report).
from pandas import DataFrame
import numpy as np
import pandas as pd

from OPT4_VolatilitySystem import OPT4_VolatilitySystem

from technical.util import resample_to_interval


class OPT5_GateBase(OPT4_VolatilitySystem):
    gate2_kind = "none"        # none | er1h | er3h | chop | mlc
    gate2_er_min = 0.25        # ER threshold (er1h / er3h variants)
    gate2_chop_max = 61.8      # Choppiness ceiling (chop variant)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        # --- gate2 column: 1h Kaufman efficiency ratio ER(28) -----------------
        er_n = 28
        net_move = (dataframe["close"] - dataframe["close"].shift(er_n)).abs()
        path_len = dataframe["close"].diff().abs().rolling(er_n, min_periods=er_n).sum()
        dataframe["g2_er1h"] = net_move / path_len

        # --- gate2 column: 3h Kaufman ER(14) -----------------------------------
        # Fresh 3h resample identical in mechanism to the OPT1 signal frame
        # (180 min); value lands on the 1h row where the 3h candle completes.
        r3 = resample_to_interval(dataframe, 180)
        net3 = (r3["close"] - r3["close"].shift(14)).abs()
        path3 = r3["close"].diff().abs().rolling(14, min_periods=14).sum()
        r3["g2_er3h"] = net3 / path3
        r3["date_merge"] = r3["date"] + pd.Timedelta(minutes=180 - 60)
        dataframe = dataframe.merge(
            r3[["date_merge", "g2_er3h"]],
            how="left", left_on="date", right_on="date_merge",
        ).drop(columns="date_merge")
        dataframe["g2_er3h"] = dataframe["g2_er3h"].ffill()

        # --- gate2 column: 1h Choppiness(14) -----------------------------------
        prev_close = dataframe["close"].shift(1)
        tr = pd.concat(
            [
                dataframe["high"] - dataframe["low"],
                (dataframe["high"] - prev_close).abs(),
                (dataframe["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        hh = dataframe["high"].rolling(14, min_periods=14).max()
        ll = dataframe["low"].rolling(14, min_periods=14).min()
        dataframe["g2_chop"] = (
            100.0 * np.log10(tr.rolling(14, min_periods=14).sum() / (hh - ll)) / np.log10(14)
        )

        # --- gate2 column: 12h EMA(50) slope (directional gate) ----------------
        r12 = resample_to_interval(dataframe, 720)
        r12["g2_mlc_ema"] = r12["close"].ewm(span=50, min_periods=50).mean()
        r12["g2_mlc_slope"] = r12["g2_mlc_ema"].diff()
        r12["date_merge"] = r12["date"] + pd.Timedelta(minutes=720 - 60)
        dataframe = dataframe.merge(
            r12[["date_merge", "g2_mlc_slope"]],
            how="left", left_on="date", right_on="date_merge",
        ).drop(columns="date_merge")
        dataframe["g2_mlc_slope"] = dataframe["g2_mlc_slope"].ffill()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # OPT4 raw signals + atr08 gate first; gate2 can only remove entries.
        dataframe = super().populate_entry_trend(dataframe, metadata)
        kind = self.gate2_kind
        if kind == "er1h":
            ok = (dataframe["g2_er1h"] >= self.gate2_er_min).fillna(False)
            dataframe.loc[~ok, ["enter_long", "enter_short"]] = 0
        elif kind == "er3h":
            ok = (dataframe["g2_er3h"] >= self.gate2_er_min).fillna(False)
            dataframe.loc[~ok, ["enter_long", "enter_short"]] = 0
        elif kind == "chop":
            ok = (dataframe["g2_chop"] <= self.gate2_chop_max).fillna(False)
            dataframe.loc[~ok, ["enter_long", "enter_short"]] = 0
        elif kind == "mlc":
            up = (dataframe["g2_mlc_slope"] > 0).fillna(False)
            dn = (dataframe["g2_mlc_slope"] < 0).fillna(False)
            dataframe.loc[~up, "enter_long"] = 0
            dataframe.loc[~dn, "enter_short"] = 0
        return dataframe
