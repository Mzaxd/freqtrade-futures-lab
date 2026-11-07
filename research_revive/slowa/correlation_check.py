# -*- coding: utf-8 -*-
"""慢A模拟 vs 冻结A袖实际wallet: 月度收益相关性 + S3h校验质量 (research_revive/slowa)"""
import numpy as np
import pandas as pd

OUT = "/Users/caihaohan/Code/freqtrade-futures-lab/research_revive/slowa"
ZIP_W = ("/Users/caihaohan/Code/freqtrade-futures-lab/user_data/backtest_results/"
         "backtest-result-2026-11-07_03-54-11.zip")

# --- A 袖实际月度收益 (wallet feather) ---
import zipfile, tempfile, os
tmp = tempfile.mkdtemp()
with zipfile.ZipFile(ZIP_W) as z:
    z.extract("backtest-result-2026-11-07_03-54-11_ARL_2x_wallet.feather", tmp)
w = pd.read_feather(os.path.join(tmp, "backtest-result-2026-11-07_03-54-11_ARL_2x_wallet.feather"))
we = w.set_index("date")["total_quote"].resample("D").last().ffill()
a_month = we.resample("ME").last().pct_change().dropna()
a_month.index = a_month.index.to_period("M").astype(str)

# --- 模拟月度 ---
print("月度收益相关性 (2021-01..2026-10, n=70):")
print(f"  变体     corr    A月σ    慢月σ   同号月占比")
for v in ["S3h", "S12h", "S24h", "D20_10"]:
    m = pd.read_csv(f"{OUT}/sim_{v}_monthly.csv")
    m = m.set_index("month")["pnl_eq"]
    # 模拟 pnl_eq 是月内盈亏/当时权益近似(逐笔口径), 转月收益率: 简单除以累计
    df = pd.DataFrame({"a": a_month, "s": m}).dropna()
    corr = df["a"].corr(df["s"])
    same = (np.sign(df["a"]) == np.sign(df["s"])).mean()
    print(f"  {v:8s} {corr:+.3f}  {df['a'].std()*100:5.1f}%  {df['s'].std()*100:5.2f}%  {same*100:4.0f}%")

# --- 2024-26 子窗相关 (慢A潜在分散价值所在) ---
print("\n2024-01..2026-10 子窗 (n=34):")
for v in ["S3h", "S12h", "S24h", "D20_10"]:
    m = pd.read_csv(f"{OUT}/sim_{v}_monthly.csv").set_index("month")["pnl_eq"]
    df = pd.DataFrame({"a": a_month, "s": m}).dropna()
    df24 = df[df.index >= "2024-01"]
    corr = df24["a"].corr(df24["s"])
    same = (np.sign(df24["a"]) == np.sign(df24["s"])).mean()
    print(f"  {v:8s} corr={corr:+.3f}  同号 {same*100:4.0f}%  慢A正月占比 {100*(df24['s']>0).mean():.0f}%  A正月占比 {100*(df24['a']>0).mean():.0f}%")

# --- S3h 校验质量: 逐年笔数 vs 实际 ---
tr_real = pd.read_csv(f"{OUT}/a_sleeve_trades.csv", parse_dates=["close_date"])
tr_real["year"] = tr_real["close_date"].dt.year
tr_sim = pd.read_csv(f"{OUT}/sim_S3h_trades.csv")
cmp = pd.DataFrame({
    "实际笔数": tr_real.groupby("year").size(),
    "模拟笔数": tr_sim.groupby("year").size(),
}).fillna(0).astype(int)
print("\nS3h 校验 — 逐年笔数:")
print(cmp.to_string())
print("\n实际 exit_reason 分布:", tr_real["exit_reason"].value_counts().to_dict())
print("模拟 reason 分布:", tr_sim["reason"].value_counts().to_dict())
print("\n实际逐年收益% (wallet): ")
ye = we.resample("ME").last()
y0 = ye.resample("YE").first(); y1 = ye.resample("YE").last()
print(((y1 / y0 - 1) * 100).round(1).to_string())
