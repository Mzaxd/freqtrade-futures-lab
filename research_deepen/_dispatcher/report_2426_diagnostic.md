# 三 sleeve 组合 2024-26 披露式部署诊断 + 21-26 拼接总览

> 性质：**[披露式诊断]**，非 OOS。2024-26 对 VolSys(A)/NFI(N) 已烧毁；**MomRegime(B) 本次首次消耗**
> （预登记见 [PREREG_2426_diagnostic.md](PREREG_2426_diagnostic.md)，先于回测写就）。
> 执行：调度员（DP_ 前缀子类，冻结参数零改动，12 币 OPT7_config_12p，fee 0.0005）。

## 1. 单 sleeve 2024-01-01 → 2026-09-12

| Sleeve | 回测总收益 | freqtrade DD | mtm 口径收益/DD | 笔数 | 年度拆分 24/25/26 |
|---|---|---|---|---|---|
| A（DP_OPT4） | **+96.8%** | 42.3% | +93.8% / **-45.8%** | 464 | +79.0 / -6.4 / +15.7% |
| B（DP_SleeveB） | **+117.4%** | 39.7% | +104.8% / -43.7% | 113 | +69.0 / **+23.6** / -2.0% |
| N（DP_NFILite, tc3） | **+11.2%** | 4.9% | +11.2% / -5.5% | 71 | +9.3 / +0.2 / +1.6% |

- A 与 phase-4 披露式回归（+102.6%/DD 42.3%）吻合；小差异来自 LINK/DOT/LTC/UNI 现为真实 funding。
- 互补性清晰：A 挣 2024 与 2026，**B 挣 2025 熊市**（+23.6%），N 全程小正。

## 2. 组合聚合（日度再平衡固定权重，与 PRT 同口径）

| 段 | 权重 | 总收益 | CAGR | Sharpe | maxDD(from-peak) | 30 天滚动 maxDD |
|---|---|---|---|---|---|---|
| 21-23（池内，PRT 复现） | 45/25/30 | +918% | 116.9% | 2.51 | **-14.7%** | — |
| **24-26（诊断）** | **45/25/30** | **+85.2%** | **+25.6%** | **0.98** | **-25.3%**（2026-08-04） | **-14.4%**（2025-02-03） |
| 24-26（诊断） | 40/40/20 | +98.3% | +28.9% | 0.98 | -28.3% | -15.5% |
| 21-26 拼接 | 45/25/30 | +1785% | +67.5% | 1.85 | -25.3% | -14.4% |

**红线判定**：dry-run 规则（30 天滚动 DD>20% 停机）在 24-26 全程**未被触发**（最深 -14.4%）；
A 单体同期 30 天滚动 DD 达 **-25.1%**（会触线停机）——组合形态的价值得到窗口内实证。

## 3. 对 phase-7 S1 holdout 的更正（重要）

S1 记载 NFI-Lite holdout = "+1.0%、7 笔、仅 SOL/ETH 触发、2026 年 0 笔"，并解读为"慢牛无投降形态"。
本次复盘发现该 holdout 实际运行在 **3 币有效宇宙**：旧实验室环境中 9 个山寨币的 5m 数据止于 2023-12-31
（OSS 阶段"9 币 × 2021-2023"数据集），freqtrade 对无数据币对静默跳过（per-pair 表 0 笔）。
**决定性验证**：BTC/ETH/SOL 三币重跑精确复现 7 笔 / +0.95% / 胜率 57.1% / DD 1.0%（`dp_nfilite_3p_verify.zip`）。
全宇宙（12 币）真实数字为 **71 笔 / +11.2% / DD 4.9%**（`dp_nfilite_2426.zip`）。

- 更正后的结论：投降抄底形态在 24-26 的山寨币上**存在且为正**（62 笔），只是在三大币上稀疏；
  "危机保险型 sleeve"的定性仍成立（收益温和、DD 极低），但"几乎不交易"的极端稀疏性是数据伪影。
- 账本处理：S1 holdout 数字标注 [已修正：宇宙伪影]；本次 12 币全窗为该家族 24-26 的正式披露数字。

## 4. 局限与披露

1. 24-26 为已烧毁窗口（A/N）+ 本次新烧（B）：一切数字仅用于部署风险画像，不得反推调参（预登记约束）。
2. 拼接曲线在 2024-01-01 边界重置复利路径（分段收益率拼接，已避免水平跳空伪影；脚本初版有此 bug，已修复并复算）。
3. mtm 口径 DD 深于 freqtrade 账户 DD（含持仓浮亏），与 PRT 的口径差异一致。
4. 40/40/20 在 24-26 赚更多（+98.3%）但 DD 更深（-28.3%）；两个权重点都给出，维持 PRT 推荐的 45/25/30
  （更稳）不因本段结果改判——预登记第 2 条。
5. 建议补充监控：30 天红线之外，增加"从峰值 -25% 人工复核"触发器（24-26 的 from-peak DD 恰好 -25.3%，
   30 天口径看不见慢性失血）。

## 5. 复现

```bash
# 三腿回测（12 币）
.venv/bin/freqtrade backtesting --userdir user_data --config user_data/configs/OPT7_config_12p.json \
  --strategy-path research_deepen/_dispatcher/strategies --strategy {DP_OPT4|DP_SleeveB|DP_NFILite} \
  --timerange 20240101-20260912 --export trades --cache none
# 三币验证（S1 伪影复现）
.venv/bin/freqtrade backtesting --userdir user_data --config user_data/configs/config_futures.json \
  --strategy-path research_deepen/_dispatcher/strategies --strategy DP_NFILite --timerange 20240101-20260912 ...
# MTM 重建与聚合
.venv/Scripts/python.exe research_deepen/_dispatcher/scripts/dp_mtm.py <zip> {A|B|N} 2024-01-01 2026-09-13
.venv/Scripts/python.exe research_deepen/_dispatcher/scripts/dp_aggregate.py
```
