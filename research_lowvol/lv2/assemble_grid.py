# -*- coding: utf-8 -*-
"""LV2 assemble_grid.py — 低波市组合装配网格(线性日度再平衡近似)。

方法声明(近似性):
  组合日收益 r_p(t) = Σ_i w_i · r_i(t);SlowA 放大 = w_S·k·r_SlowA(t),k∈{1,2,3}
  (杠杆近似:假设 k 倍敞口无保证金/资金费/强平交互,日收益线性放大)。
  组合权益 = Π(1+r_p) —— 这对"每日再平衡回固定权重"是精确的;
  与真实 freqtrade 合并回测(日内结算/保证金交互/跨袖资金占用)有偏差,wave2 真跑验证。

网格(共 50 格,全部计算全部存表):
  F1 冻结 A/B 基座 (A,B) ∈ {(70,30),(60,40),(50,50)}:
      SlowA 权重 w∈{0,10,20,30,40}% × k∈{1,2,3}(w 从 A 份额扣;w=0 时 k 无意义只记 1 格)
  F1 附加形态: A=0, B=30, SlowA=70% × k∈{2,3}
  F2 ★ 变体(曲线已找到,附加入账): (A_vt,B_vt)=70/30 基座,
      w∈{0,10,20,30,40} × k∈{2,3}(k=1 不入账以守 charter §4 ≤50 格预算)

判定(charter S1-S4,预注册不许改):
  S1: y2025 ≥ +36% 且 y2026 ≥ +22%
  S2: y2024 ≥ +44%
  S3: 全窗口总收益 ≥ +1500%
  S4: 组合 dd30 ≥ -30%;单袖 maxDD ≤ 50%(SlowA×k 用实际 cumprod(1+k·r) 计算)

输出: grid_results.csv / pareto.csv / sensitivity.csv / monthly worst 列内含
"""
import numpy as np
import pandas as pd

LAB = "/Users/caihaohan/Code/freqtrade-futures-lab"
OUT = f"{LAB}/research_lowvol/lv2"

daily = pd.read_csv(f"{OUT}/sleeves_daily.csv", parse_dates=["date"]).set_index("date")
rets = daily / daily.shift(1) - 1
rets.iloc[0] = 0.0


def sleeve_maxdd_k(s, k):
    """SlowA 放大 k 倍后的单袖 maxDD(实际计算,非线性外推)。"""
    eq = (1 + k * rets[s]).cumprod()
    return float((eq / eq.cummax() - 1).min() * 100)


def build_cell(family, wa, wb, ws, k, a_col, b_col):
    rp = wa * rets[a_col] + wb * rets[b_col]
    if ws > 0:
        rp = rp + ws * k * rets["SlowA"]
    eq = (1 + rp).cumprod()
    y = eq.groupby(eq.index.year)
    yearly = (y.last() / y.first() - 1) * 100
    dd30 = float((eq / eq.rolling(30).max() - 1).min() * 100)
    mdd = float((eq / eq.cummax() - 1).min() * 100)
    m = eq.resample("ME").last()
    worst_month = float(((m / m.shift(1) - 1) * 100).min())
    total = float((eq.iloc[-1] - 1) * 100)
    row = dict(
        family=family, sleeve_A=a_col, sleeve_B=b_col,
        wA=round(wa, 2), wB=round(wb, 2), wS=round(ws, 2), k=k,
        y2021=round(yearly.get(2021, np.nan), 1),
        y2022=round(yearly.get(2022, np.nan), 1),
        y2023=round(yearly.get(2023, np.nan), 1),
        y2024=round(yearly.get(2024, np.nan), 1),
        y2025=round(yearly.get(2025, np.nan), 1),
        y2026=round(yearly.get(2026, np.nan), 1),
        total_pct=round(total, 1),
        dd30_worst=round(dd30, 1),
        maxdd=round(mdd, 1),
        worst_month=round(worst_month, 1),
    )
    row["S1"] = bool(row["y2025"] >= 36 and row["y2026"] >= 22)
    row["S2"] = bool(row["y2024"] >= 44)
    row["S3"] = bool(total >= 1500)
    row["S4_dd30"] = bool(dd30 >= -30)
    # 单袖 maxDD ≤50%:A 34.9 / B 15.3 / A_vt 43.5 / B_vt 34.2(sleeve_check 实测);SlowA×k 实算
    smax = sleeve_maxdd_k("SlowA", k) if ws > 0 else 0.0
    row["slowA_k_maxdd"] = round(smax, 1)
    row["S4_sleeve"] = bool(smax >= -50)
    row["S4"] = bool(row["S4_dd30"] and row["S4_sleeve"])
    row["pass_count"] = int(row["S1"]) + int(row["S2"]) + int(row["S3"]) + int(row["S4"])
    return row


cells = []
# ---- F1: 冻结 A/B 基座 ----
for (b0, b1) in [(0.70, 0.30), (0.60, 0.40), (0.50, 0.50)]:
    cells.append(build_cell("F1", b0, b1, 0.0, 1, "A", "B"))
    for w in [0.10, 0.20, 0.30, 0.40]:
        for k in [1, 2, 3]:
            cells.append(build_cell("F1", b0 - w, b1, w, k, "A", "B"))
# ---- F1 附加形态: A=0, B=30, SlowA=70×k ----
for k in [2, 3]:
    cells.append(build_cell("F1x", 0.0, 0.30, 0.70, k, "A", "B"))
# ---- F2: ★ 变体 (A_vt, B_vt) 70/30 ----
cells.append(build_cell("F2", 0.70, 0.30, 0.0, 1, "A_vt", "B_vt"))
for w in [0.10, 0.20, 0.30, 0.40]:
    for k in [2, 3]:
        cells.append(build_cell("F2", 0.70 - w, 0.30, w, k, "A_vt", "B_vt"))

g = pd.DataFrame(cells)
assert len(g) == 50, len(g)
g["cell_id"] = g.index
g["s1_margin"] = np.minimum(g["y2025"] - 36, g["y2026"] - 22)
g.to_csv(f"{OUT}/grid_results.csv", index=False)

# ---- 帕累托前沿(目标:最大化 y2025 / y2026 / total_pct / dd30_worst)----
objs = ["y2025", "y2026", "total_pct", "dd30_worst"]
V = g[objs].to_numpy()
is_front = np.ones(len(g), dtype=bool)
for i in range(len(g)):
    for j in range(len(g)):
        if i == j:
            continue
        if np.all(V[j] >= V[i]) and np.any(V[j] > V[i]):
            is_front[i] = False
            break
g["pareto"] = is_front
g[g["pareto"]].sort_values("dd30_worst", ascending=False).to_csv(f"{OUT}/pareto.csv", index=False)

# ---- 敏感性: SlowA 收益打 8 折(k → 0.8k)对 top 候选 ----
def rerun_s1(row, disc=0.8):
    rp = row["wA"] * rets[row["sleeve_A"]] + row["wB"] * rets[row["sleeve_B"]]
    if row["wS"] > 0:
        rp = rp + row["wS"] * row["k"] * disc * rets["SlowA"]
    eq = (1 + rp).cumprod()
    y = eq.groupby(eq.index.year)
    yearly = (y.last() / y.first() - 1) * 100
    dd30 = float((eq / eq.rolling(30).max() - 1).min() * 100)
    total = float((eq.iloc[-1] - 1) * 100)
    return dict(
        cell_id=row["cell_id"], y2025=round(yearly.get(2025, np.nan), 1),
        y2026=round(yearly.get(2026, np.nan), 1),
        y2024=round(yearly.get(2024, np.nan), 1),
        total_pct=round(total, 1), dd30_worst=round(dd30, 1),
        S1=bool(yearly.get(2025, 0) >= 36 and yearly.get(2026, 0) >= 22),
        S2=bool(yearly.get(2024, 0) >= 44),
        S3=bool(total >= 1500),
        S4=bool(dd30 >= -30),
    )

# top3: 先按 pass_count,再按 S1 最小余量,再按 total
rank = g.sort_values(["pass_count", "s1_margin", "total_pct"], ascending=[False, False, False])
top3 = rank.head(3)
sens = pd.DataFrame([rerun_s1(r) for _, r in top3.iterrows()])
sens.to_csv(f"{OUT}/sensitivity.csv", index=False)

pd.set_option("display.width", 250)
print(f"cells={len(g)}  S1过={int(g['S1'].sum())}  S1-S4全过={int((g['pass_count']==4).sum())}")
print("\n== top3 ==")
print(top3[["cell_id", "family", "sleeve_A", "sleeve_B", "wA", "wB", "wS", "k",
            "y2021", "y2022", "y2023", "y2024", "y2025", "y2026", "total_pct",
            "dd30_worst", "maxdd", "worst_month", "pass_count"]].to_string(index=False))
print("\n== 帕累托前沿 ==")
print(g[g["pareto"]][["cell_id", "family", "wA", "wB", "wS", "k", "y2024", "y2025", "y2026",
                      "total_pct", "dd30_worst", "pass_count"]].sort_values("dd30_worst", ascending=False).to_string(index=False))
print("\n== 敏感性(SlowA ×0.8)==")
print(sens.to_string(index=False))
print("\nsaved: grid_results.csv / pareto.csv / sensitivity.csv")
