# 组合层深化报告（portfolio）— 2026-09-14

> **产出方式披露**：PRT agent 完成全部计算管线（prt00–prt09，结果 CSV 齐全）后在最终写作阶段被平台内容过滤误杀；
> 本报告由调度员基于其结果文件补写，未重算、未挑选、无新增数字。所有结果文件在 `results/`，脚本在 `scripts/`（按编号顺序重跑即可复现）。
> 结论级别：**[推断强化(组合)]** —— 对冻结 sleeve 的组合统计，非新 alpha。

## 1. 数据与口径

- Sleeve 来源（zip 内容校验后解包）：
  - **A** = OPT4_VolatilitySystem 12 币 IS（`opt4_VolatilitySystem_12p_is`）
  - **B** = OPT2_MomRegime15mLb21 全窗重跑 `prt_B_momregime15mlb21_full.zip`（12 币 2021-01→2023-12，+1950% realized）
  - **N** = NFI-Lite（`opt7_lite_tc3_12p_is`）
  - **S** = SuperDD（`opt7_pool12_A_OPT7_SuperDD_A`，仅 4-sleeve 试验用）
- 两种日收益口径（`prt03/prt05`）：
  - **realized**：闭仓交易盈亏按日归集（phase-7 用的月度闭仓法的日频版）；
  - **mtm**：回测逐日权益曲线 mark-to-market（**包含持仓浮亏**，是风险口径）。
  - 全部评估 ≤ 2023-12-31。

## 2. Sleeve 单体（`summary_sleeves.csv`）

| Sleeve | 总收益 | CAGR | Sharpe(realized/mtm) | maxDD realized | maxDD mtm |
|---|---|---|---|---|---|
| A（OPT4） | +1495.8% | 152% | 1.83 / 2.17 | -14.9% | **-21.1%** |
| B（MomRegime） | +1950.0% | 174% | 1.29 / 1.81 | -24.8% | **-35.1%** |
| N（NFI-Lite） | +63.5% | 17.9% | 2.74 / 2.75 | -3.1% | -3.1% |
| S（SuperDD） | +82.4% | 22.2% | 1.03 / 1.07 | -27.5% | -27.9% |

## 3. 相关性推断强化（`corr_bootstrap.csv`，平稳 bootstrap ≥10k，95% CI）

| 口径 | corr(A,B) | corr(A,N) | corr(S,B) |
|---|---|---|---|
| 日频 mtm | **0.44** [0.31, 0.54] | 0.11 [0.03, 0.21] | 0.49 [0.40, 0.58] |
| 月度 realized | 0.24 [0.07, 0.61] | 0.23 [0.04, 0.47] | 0.08 [-0.13, 0.33] |
| 月度 mtm | 0.65 [0.42, 0.79] | 0.13 [-0.09, 0.51] | 0.71 [0.58, 0.88] |

**修正 phase-7 的关键数字**：phase-7 报 corr(A,B)=0.096，那是月度闭仓聚合 + B 用 IS/VAL 拼接窗的产物。日频 mtm 口径下 A-B 实际相关 **0.44**、月度 mtm 下 0.65——A 与 B 都是波动/趋势暴露，持仓期间同涨同跌。NFI-Lite 仍是真分散器（corr(A,N)≈0.11）。

## 4. 权重网格与不确定性（`grid_scan_*.csv`、`weights_bootstrap.csv`）

- mtm 口径网格顶点：**A40/B20/N40 → Calmar 8.20 / DD -12.1% / Sharpe 2.57**；前 10 名全部 B≤0.25。
- 40/40/20（phase-7 推荐）：mtm Calmar 7.37 / **DD -18.6%** / Sharpe 2.37；等权：Calmar 6.49 / DD -17.1%。
- A 单独：mtm Calmar 5.77 / DD -25.9% → **组合增益真实但温和**（Calmar +28%，DD -7pp），远小于 phase-7 月度闭仓口径显示的幅度。
- Bootstrap：argmax 相对 40/40/20 的 Calmar 增益 0.82 [0.11, 3.48]（mtm）——**最优点与推荐点的差异在噪音量级内，宽带区域内选择不敏感**。

## 5. 动态权重与 4-sleeve（`dyn4_results.csv`）

- 月度逆波动率（63d 窗）：mtm Calmar 7.97 vs 静态 40/40/20 的 7.37——小幅占优，但无 bootstrap 支持，视作噪音级差异，不值得为它加复杂度。
- **SuperDD 入组合全面失败**：任何 +S pro-rata 方案都劣于 3-sleeve 最优（corr(A,S) 0.36-0.62，趋势预算重复），与 phase-7 的谨慎判断一致。

## 6. 结论

1. **phase-7 组合层数字需要打折**：Calmar 18.15 / DD 6.92% 是月度闭仓聚合的口径效应；日频 mtm 下诚实的组合增益是 Calmar 5.8→7.4~8.2、单体 DD -26%→-12~-19%。
2. **B 的权重应显著下调**：网格一致指向 B∈[20%, 25%]，phase-7 的 40% 建立在低估的 A-B 相关性上。
3. **部署推荐**：**A 40-45% / B 20-30% / N 25-40%** 稳健区域内取一点（如 A45/B25/N30：mtm Calmar 6.72 [2.13, 16.75]，DD -17.0% [-30.5%, -11.5%]）；NFI-Lite 上限受其低频容量约束，不宜超 40%。
4. SuperDD 不入组合；动态权重暂缓。

## 7. 局限

- 池内 2021-23 烧毁窗口，[推断强化] 级：数字描述"已发生历史的组合结构"，外推需未来数据确认。
- B 为全窗重跑（12 币 2021-23），与 phase-7 的 IS+VAL 拼接口径不同，单体数字不可直接对表。
- NFI-Lite 的价值在崩盘月（评估窗内样本少），其真实分散力可能仍被低估。

## 8. 复现

```bash
cd 仓库根
# 依次运行（脚本自含路径与说明）：
.venv/Scripts/python.exe research_deepen/portfolio/scripts/prt00_inspect.py   # zip 盘点
# prt01–prt09 按编号顺序（B 全窗重跑在 prt04；网格 prt07；bootstrap prt08；动态 prt09）
```
