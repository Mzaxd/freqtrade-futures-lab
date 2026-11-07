# -*- coding: utf-8 -*-
"""LV1 — 变体与 A 袖(ARL_2x)的月度收益相关性(无交易月=0 填充)。"""
import json
import sys
import zipfile

import pandas as pd


def monthly(zip_path: str, name: str) -> pd.Series:
    z = zipfile.ZipFile(zip_path)
    wn = [n for n in z.namelist() if n.endswith("_wallet.feather")][0]
    w = pd.read_feather(z.open(wn))
    w["date"] = pd.to_datetime(w["date"], utc=True)
    eq = w.set_index("date")["total_quote"].resample("D").last().ffill()
    jn = [n for n in z.namelist() if n.endswith(".json") and "config" not in n][0]
    s = json.loads(z.read(jn))["strategy"][name]
    eq.iloc[-1] = float(s["final_balance"])   # 末值锚定
    m = eq.resample("ME").last()
    m0 = eq.resample("ME").first()
    m0.iloc[0] = float(s["dry_run_wallet"])
    ret = m / m0 - 1.0
    ret.index = ret.index.tz_convert("UTC")
    return ret


if __name__ == "__main__":
    A = monthly("user_data/backtest_results/backtest-result-2026-11-07_03-54-11.zip",
                "ARL_2x")
    for zpath, name in zip(sys.argv[1::2], sys.argv[2::2]):
        v = monthly(zpath, name)
        df = pd.concat([A.rename("A"), v.rename(name)], axis=1).fillna(0.0)
        full = df["A"].corr(df[name])
        late = df[df.index >= "2024-01-01"]
        print(f"{name}: 月度相关 vs A 全窗 {full:.2f} / 24-26 {late['A'].corr(late[name]):.2f}")
