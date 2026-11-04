# WS-R3 — A sleeve 震荡态防守削减 overlay：结论报告（2026-11-04）

## 0. 结论（先行）

**R3 按预注册 §4 标准被证伪：不予采纳。**

- IS（2021-23）选择胜者 = **R3_C3h_N3_D30**（G3 失败簇减半，N=3/D=30）：IS Calmar 80.38
  （基线 76.67），收益保留率 **101.2%**（≥60% 无风险标注）。次优 = R3_C3p_N3_D30（暂停版，79.41）。
  前两名均为 G3 主假设族，市场门（G2 78.96 为最好）未能胜出——与预注册 §2.1 锚窗口预判一致。
- OS（2024-01-02..2026-09-12）两段验收：
  - 震荡窗口回撤改善：C3h **+0.00pp**、C3p **+3.95pp** —— **双双 FAIL**（标准 ≥+5pp）；
  - 趋势窗口年化损失：C3h **−0.47pp**（反而更好）、C3p +1.76pp —— 双双 PASS（标准 ≤2pp）。
- 组合层（0.7×A'+0.3×B3，OS）：两变体 maxDD −30.99%→−29.10/−29.18%，总收益 +86.5%→+87.8/+93.4%，
  MC p95 30dDD −16.80%→−16.60/−16.61%（**改善 +0.20/+0.19pp，红线 [恶化>2pp 否决] 未触发**）。
- 定性：G3 overlay 方向正确但幅度不足——OS 全部指标轻微变好、无一变差、无红线风险，但达不到
  预注册的"+5pp 震荡回撤改善"门槛。**建议不替换冻结 A；C3p（+3.95pp）是离门槛最近的形态，
  若未来重新预注册可从 N×D 密度与暂停时长入手，但本轮不允许回头调参。**

## 1. 基线复现与对账

- 全窗 20210101-20260912 ARL_2x（3 币，模板命令）：**472 笔 / +2278.62% / DD 34.85%**，与
  research_ab 已知数字（hyperopt_A.md：472 / +2278.62% / 34.85%）**逐位一致**。
  zip → `research_chop/results/R3_base_ARL2x_full.zip`；日曲线 → `research_chop/logs/mtm_daily_R3BASE.csv`
  （dp_mtm 重建，2081 天，末值 237,862.2 = 10000+227,862.2）。
- OS 窗独立基线（20240102-20260912，新起钱包 10k）：**264 笔 / +88.02% / DD 34.84%**，与
  research_ab console log（hptA_base_2426）逐位一致。
- **披露（对账源切换）**：`research_ab/results/hptA_base_ARL2x_IS.zip` 内含策略键
  `TrendBaselineV1`（19 笔，2021-01..03 窗）、`hptA_base_ARL2x_2426.zip` 内含
  `NostalgiaForInfinityX7`（0 笔）——两个 zip 均为错标/损坏（正是 CONTEXT 红线 2 所指教训的
  实例）。对账改用 research_ab 的 console log 数字（IS 207 笔/+1213.16%/DD 13.96%），全部吻合。

## 2. 变体 × 窗口收益表

IS = 20210101-20240101（设计窗）；OS = 20240102-20260912（只裁决）。
Calmar/DD 口径：dp_mtm 日曲线（含持仓 MTM，INIT=10000；与 freqtrade 报告口径略有差异，见 §7）。

| 变体 | IS 笔数 | IS 总收益 | IS maxDD | IS Calmar | IS 保留率 | OS 笔数 | OS 总收益 | OS maxDD |
|---|---|---|---|---|---|---|---|---|
| BASE（ARL_2x） | 207 | +1213.3% | −15.83% | 76.67 | 1.000 | 264 | +88.0% | −39.7% |
| R3_G1h（阴性对照） | 207 | +470.2% | −8.28% | 56.77 | 0.388 | — | — | — |
| R3_G2h | 207 | +1021.6% | −12.94% | 78.96 | 0.842 | — | — | — |
| R3_G4h | 207 | +1154.6% | −15.85% | 72.84 | 0.952 | — | — | — |
| R3_C3h_N2_D14 | 207 | +1162.9% | −16.12% | 72.15 | 0.958 | — | — | — |
| R3_C3h_N2_D30 | 207 | +805.0% | −15.27% | 52.70 | 0.663 | — | — | — |
| R3_C3h_N3_D14 | 207 | +1213.2% | −15.83% | 76.66 | 1.000 | — | — | — |
| **R3_C3h_N3_D30（胜者）** | 207 | **+1227.7%** | −15.27% | **80.38** | **1.012** | 264 | +90.3% | −37.4% |
| R3_C3h_N4_D14 | 207 | +1213.2% | −15.83% | 76.66 | 1.000 | — | — | — |
| R3_C3h_N4_D30 | 207 | +1213.2% | −15.83% | 76.66 | 1.000 | — | — | — |
| R3_C3p_N3_D30（次优） | 205 | +1191.7% | −15.01% | 79.41 | 0.982 | 256 | +98.2% | −37.4% |

- 选择规则（预注册）：IS Calmar 最高者胜出 → C3h_N3_D30；C3p 只在 IS 结束后跑 C3h 最优 N/D
  （N3_D30）一格（省算规则披露于此）。胜者保留率 101.2%（>60%，无风险标注）。
- 全部非阻断变体 IS 笔数恒为 207 且逐笔 open_date 与基线一致（半仓化不改入场）；C3p 阻断 2 笔
  （207→205）。市场门/C3h 的 per-pair 笔数 BTC 93/ETH 65/SOL 49 与基线完全一致。

## 3. G1 阴性对照（预注册预期 ≈ 全局 risk×0.5，不判别）

G1（|mom_z|<1.25）在 IS **95.7% 的入场时点为 ON**（198/207 笔被减半；门的小时占有率 73-75%，
但入场集中在波动突破失败时点 → 入场条件占有率达 95.7%）。结果：保留率 38.8%、Calmar 56.77
低于基线 76.67——近乎全局 risk×0.5，DD 虽 −15.83→−8.28% 但收益破坏过大，**不判别性得到确认**，
与 PRE §2.1 的预判一致。G1 降级为阴性对照的决策被本轮结果支持。

## 4. G3 网格全景（主假设）

- **触发密度极低**：N3_D14、N4_D14、N4_D30 三格在 IS 从未触发（结果与基线完全一致）；N2 两格
  过度触发（保留率 0.66-0.96）；唯一兼顾"触发且不误伤"的格 = **N3_D30：IS 仅减半 8/207 笔（3.9%）**，
  保留率 101.2% —— 8 笔减半恰覆盖簇后连败入场，避开亏损 > 新增收益，Calmar +4.8%。
- C3p（同 N/D，7 天暂停）：IS 阻断 2 笔、保留率 98.2%、DD −15.01%（全网格最浅）。
- 机制解读：3 币宇宙下单 (pair,side) 的 30 天失败簇密度远低于 12 币全局（P2 原设定 N=2/24h/48h
  是 12 币密度），密度重标定后"防守"集中在极少数簇尾入场。

## 5. OS 裁决（预注册 §4）

震荡/趋势日集：per-pair 小时 g2|g4 → 当日 OR → **shift(1)**（D 日用 D-1 日标签）→ 3 币 ANY-OR。
OS 984 个收益日中震荡日 496（50.4%）。

| 指标 | BASE | C3h_N3_D30 | C3p_N3_D30 | 判定 |
|---|---|---|---|---|
| 震荡窗口子序列 maxDD | −26.26% | −26.26% | **−22.31%** | 改善 +0.00 / +3.95pp，**均 < +5pp → FAIL** |
| 趋势日年化收益（子序列几何年化） | 12.56% | 13.03% | 10.80% | 损失 −0.47 / +1.76pp，**均 ≤2pp → PASS** |
| OS 全窗 maxDD（dp_mtm） | −39.72% | −37.35% | −37.44% | （参考） |
| OS 全窗最差 30d 滚动 | −16.52% | −16.52% | −16.52% | （参考，同一最深窗） |

**裁决：两项须同时通过才算有效 → R3 无效（falsified）。** C3p 在震荡窗方向正确（+3.95pp）但
未达门槛；C3h 胜者对震荡窗几乎无影响（IS 的改善来自 2023 年簇，未迁移到 2026 型震荡）。

## 6. 组合层（0.7×A' + 0.3×B3，OS 窗；ws2 拼接法）

| 组合 | OS 总收益 | OS maxDD | 最差 30d | MC med 30dDD | **MC p95 30dDD** | vs 基线 | 红线（恶化>2pp） |
|---|---|---|---|---|---|---|---|
| 基线 AB | +86.5% | −30.99% | −12.64% | −13.45% | **−16.80%** | — | — |
| AB × C3h_N3_D30 | +87.8% | −29.10% | −12.68% | −13.30% | **−16.60%** | +0.20pp | 不触发 |
| AB × C3p_N3_D30 | +93.4% | −29.18% | −12.67% | −13.30% | **−16.61%** | +0.19pp | 不触发 |

MC：30d 块自助、2000 次、seed=20261103，(rA,rB) 同日联合重采样（ws2_analysis.py 同参数复刻，
回收语义已内嵌于 A'，无 s 开关项）。**红线复核通过**（两变体均略优于基线）。

## 7. 诚实披露

1. **基线 zip 错标发现**：research_ab 侧 `hptA_base_ARL2x_{IS,2426}.zip` 内容与文件名不符
   （§1）；本轮对账改用 console log，全部吻合。本轮所有 zip 均在产出后立即以 JSON 内 strategy
   键名 + 笔数 + per-pair 笔数三重核验后才 mv。
2. **执行器 bug（已修复）**：首轮 3 个市场门 IS 结果曾为 49 笔（SOL 单币）——runner 脚本把
   `-p` 逐 pair 重复传参，argparse 只保留最后一个（SOL）。已改为单 `-p` 三币并新增"期望笔数
   守卫"（IS=207 / OS=264），损坏 zip 已删除并全部重跑；直接命令复算确认 207 笔后才进入选择。
3. **门实现一致性（预注册 §6.2，≥3 窗口）**：策略内现算门（get_pair_dataframe 因果切片 + 尾部
   800 行标记，逐字复刻 regime_label.py）与 C0 CSV 逐点对比——入场时点核验 IS 204/207、OS
   262/264 一致；日历窗核验 2022-06..09、2025-01..04、2026-02-15..04-15 三窗全 3 币 **0 不一致**；
   全部不一致集中在各回测窗头 ~1 周的 startup 部分窗口区（2021-01-01..02-01：BTC 68/744 等；
   2024-01-02..02-01 同理），即下条第 4 点的已知近似，非实现错误。
4. **startup 取舍（有意）**：为保信号层与基线逐字节一致（startup_candle_count 维承 200，不改），
   回测内 raw 帧只含窗前 200 根 → 每窗头 ~40h g4/g2 无窗可算（保守 OFF=基线行为）、头 ~520h
   g2 的 720h rank 用部分窗口（240..719 根），之后与 C0 完全一致。g1 全程精确（仅需 84h），
   G3 族不需要行情数据、全程精确。CONTEXT"720h rank 需 startup≥900"与"信号不可动"冲突时
   取后者，代价如上量化（仅窗头，且只影响 g2/g4 参考臂）。
5. **G3 语义**："止损"按任务书操作化为 profit_ratio<0 的平仓（含 exit_signal/time_stop 平仓的
  亏损单），同 pair 同边；C3h 计数 = D 窗内亏损单且晚于该边最近一次盈利平仓（PRE"直至该边
   出现盈利单"）；C3p = 以最近亏损单为锚、7 天时间解锁、该锚前 D 天簇 ≥N 才暂停，锚后同边
   盈利平仓提前解锁。数据访问复用 OPT9 P2 的 `Trade.get_trades_proxy(is_open=False)` 模式。
6. **窗口口径**：变体 IS/OS 均为独立窗回测（新钱包 10k）；基线 IS 取全窗重建曲线切片（无
   force-close），变体 IS 窗末有 force-close（边界 1-3 笔级差异）；OS 窗 G3 状态从零开始
   （无 IS 交易记忆，D≤30 仅影响 2024-01 初）。dp_mtm 重建误差 p95 ≈1382 USDT（小时 MTM
   近似，与 A3/B3 同法同源）。
7. **钱包交互**：仓位随权益复利，join 后个别笔 variant/base stake 比值最高 1.034（变体避开
   亏损后钱包略大所致）；组合层为日频固定权重拼接（ws2 方法），不模拟跨 sleeve 钱包级交互。
8. **选择效应**：胜者对基线 IS Calmar 优势仅 +4.8%，且 6 格 C3h 中 3 格零触发；N3_D30 的优势
   由 8 笔减半驱动——样本极小，OS 迁移弱正是其体现。OS 只跑了基线/胜者/次优三连，未做任何
   回头调参。
9. **口径差**：freqtrade console 的 DD（账户口径，IS 基线 13.96%）与本报告 dp_mtm DD
   （含持仓 MTM，−15.83%）不同；所有变体横向比较统一用后者。

## 8. 复现命令

```bash
# 基线全窗（§1）
.venv/Scripts/freqtrade.exe backtesting --userdir user_data \
  --config user_data/configs/OPT7_config_12p.json \
  --strategy-path user_data/strategies/oss --strategy ARL_2x \
  --timerange 20210101-20260912 -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
  --export trades --cache none
.venv/Scripts/python.exe research_deepen/_dispatcher/scripts/dp_mtm.py \
  research_chop/results/R3_base_ARL2x_full.zip R3BASE 2021-01-01 2026-09-13 \
  research_chop/logs/mtm_daily_R3BASE.csv
# 变体（串行；<EXP> = 期望笔数守卫；策略在 research_chop/strategies/R3_Gates.py）
.venv/Scripts/python.exe research_chop/scripts/r3_btrun.py R3_C3h_N3_D30 20210101-20240101 is_R3_C3h_N3_D30 207
.venv/Scripts/python.exe research_chop/scripts/r3_btrun.py R3_C3h_N3_D30 20240102-20260912 os_R3_C3h_N3_D30 264
# 分析
.venv/Scripts/python.exe research_chop/scripts/r3_is_select.py is_R3_C3p_N3_D30
.venv/Scripts/python.exe research_chop/scripts/r3_os_analysis.py
.venv/Scripts/python.exe research_chop/scripts/r3_gate_xcheck.py
```

## 9. 文件清单

- 策略：`research_chop/strategies/R3_Gates.py`（G1h/G2h/G4h + C3h×6 + C3p×6，全部继承 ARL_2x，
  信号/止损逐字不动）
- 脚本：`research_chop/scripts/{r3_btrun,r3_is_select,r3_os_analysis,r3_gate_xcheck}.py`
- 结果 zip（全部经键名+笔数核验）：`research_chop/results/R3_base_ARL2x_full.zip`、
  `R3_is_*.zip`（10 个变体）、`R3_os_{base_ARL2x,R3_C3h_N3_D30,R3_C3p_N3_D30}.zip`
- 日志/中间量：`research_chop/logs/`（各 run console log、`mtm_daily_R3BASE.csv`、
  `r3_os_daily_returns.csv`、`r3_os_analysis_output.txt`、`r3_gate_xcheck_output.txt`、
  `r3_is_selection_table.txt`、`r3_halve_fractions.txt`）
