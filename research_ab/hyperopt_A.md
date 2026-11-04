# Hyperopt-A — sleeve A（OPT9_Recycle/ARL_2x）关键参数 hyperopt：冻结参数可否被显著超越？（2026-11-04）

## 0. 结论先行

**冻结参数不可被"显著且稳健地"超越。本实验是一次不推翻既有纪律的证伪性复核。**

以 **24-26 披露窗（20240102-20260912）** 为准的判定：

1. **风险调整口径上确有"赢家"，但不是 alpha，是风险拨盘。** Sharpe 损失的 top 组合（S2：signal 2.25 / stop 2.5）在 24-26 窗把
   SharpeD 0.80→1.07、maxDD 34.84%→18.96%。但同一配置在 IS（2021-23）**每一年都更差**（三年利润 107/50/117 vs 基线 168/119/133），
   全窗利润只有基线的 59%。分年拆解显示其 24-26 优势高度不均：2024 +69%、**2025 −64%**、2026p +415%（相对）——
   这是 regime 条件下的暴露收缩（入场更严 + 名义更小），不是可迁移的改进。与 deepen INFER 的 rank IC −0.156 结论同构。
2. **Calmar 损失的 top（C1：stop 2.0→1.75，其余冻结）是唯一在 6 个年份、3 个窗口利润全部 ≥ 基线的变体**（全窗 +2931.6% vs +2278.6%），
   但代价是 DD 不降（全窗 34.91 vs 34.85）、SharpeD 全窗略降（1.33 vs 1.36）、2021 年内 DD 近翻倍（9.8% vs 5.6%）。
   机制是 1% 风险模型下的名义放大拨盘（stop 距离 −12.5% → notional ×1.14），与 lev 网格（AB_LevGrid）已证明的"真拨盘是 risk/stop"同一族。
   其 IS 目标函数优势仅 +4.0%，处于 534 次试验的选择噪声带内（见 §5）。
3. **两个损失函数选择了相反方向**（Sharpe 要更宽 stop 2.5-3.0 + signal 2.25；Calmar 要更窄 stop 1.75 + signal 保持 2.0），
   唯一共识是 resample_hours=3（冻结值）——Sharpe top-20% 中 100%、Calmar top-20% 中 72% 取 3。
   **冻结点就坐在高台上**：Sharpe 面上冻结组合位列 247 个不同组合的第 49（恰好 top-20% 边界），Calmar 面上位列 273 个的第 6。
4. **P2 熔断参数在本 3 币 sleeve 上近乎不绑定**（cluster_stop_count=3 时熔断在 IS 从未触发，6 种 window/circuit 排列结果完全相同；
   count=2 vs 3 全窗仅差 ~3 笔）。P2 的平坦是覆盖度限制（OPT9 的 P2 是在 12 币宇宙上取证/验证的，3 币下同向止损簇稀疏），
   **不是** P2 默认值最优的证据。本次网格无法对 P2 做有意义的选择。
5. 多重检验折扣后（本实验 534 次 epoch 回测 / 417 个不同组合，叠加 INFER 记载的 ~787 次历史试验，家族总数 ~1340），
   top-1 对冻结点的 IS 边际（Sharpe +5.6%、Calmar +4.0%）与"从近似并列的高台顶部挑最大值"的期望膨胀一致，不构成显著超越。

**一句话：没有发现能同时（a）在 IS 与 24-26 同向、（b）跨年份稳健、（c）经多重检验折扣后仍显著的参数组合。
冻结的 OPT1→OPT9 参数链保留；若未来要动，唯一值得单点复核的是 stop_atr_mult=1.75（C1），但它属于风险预算拨盘，
应并入风险模型专线（与 risk_pct/杠杆同审），而不是入场几何。**

---

## 1. 定位与纪律（预注册）

- **这是验证/证伪实验，不是找圣杯。** 仓库既有结论：deepen INFER 工作流（research_deepen/inference/report.md）判定
  "调参期望收益 ≈ 0"（CSCV 75 配置 × 20 切分，rank IC 均值 **−0.156**，正比例 20%；家族试验数口径 N=787）。
  本报告所有"赢家"都在该先验下解读。
- **披露：本次 grid 重开了冻结的入场几何**（signal_atr_mult / resample_hours 属 falsified-direction 红线内的参数）。
  这是任务书明确要求的单次例外，仅用于验证；不构成对该纪律的解除。实验后未修改任何冻结文件。
- 网格预注册：buy：signal_atr_mult ∈ {1.5,1.75,2.0,2.25,2.5}、resample_hours ∈ {2,3,4,6}；
  sell：stop_atr_mult ∈ {1.5,1.75,2.0,2.25,2.5,3.0}、cluster_stop_count ∈ {2,3}、cluster_window_h ∈ {24,48}、
  circuit_hours ∈ {24,48,72}。总空间 20×72=**1440**。risk_pct 不纳入（风险模型常数，另有专线）。
- 优化仅用 IS（20210101-20240101）；**24-26 窗绝对未参与任何优化**（仅验证）。
- 基线 = OPT9_Recycle→ARL_2x（RECYCLE_MULT=1.21，lev 2x，3 币）。基线全窗 472 笔 / +2278.62% / DD 34.85%（lev_ARL_2x.zip 复核一致）。

## 2. 实验设置与可复现性

- 变体文件：`user_data/strategies/oss/OPT9_Hpt.py`（**新文件**，子类 ARL_2x；把上述参数声明为 CategoricalParameter；
  唯一代码改动是 override `confirm_trade_entry` 以显式 `.value` 强转——freqtrade Parameter 不支持隐式数值转换，
  逻辑与 OPT9 逐行相同）。冻结文件未动。
- freqtrade 2026.8（optuna NSGA-III 采样器）。**每个 epoch 都设参后跑完整回测**（含 custom_stoploss /
  custom_stake_amount / confirm_trade_entry 回调，已读源码确认），sell space 回调参数被正确变化。
  resample_hours 在 populate_indicators 中 → 必须且已用 `--analyze-per-epoch`。
- 冒烟：1 epoch 确认 6 参数全部被识别（buy: resample_hours, signal_atr_mult；sell: stop_atr_mult, cluster_stop_count,
  cluster_window_h, circuit_hours）。单 epoch ≈ 43s（-j 1）→ 预算：每损失函数 300 epochs @ -j 8（32 核机器）。
- 主 run（IS 窗，--random-state 42，--spaces buy sell）：
  - Sharpe：300 请求 → **254 个 epoch 评估**（46 个重复参数被跳过），247 个不同组合，墙钟 ~33 分钟。
  - Calmar：300 请求 → **279 个 epoch 评估**（21 跳过），273 个不同组合，墙钟 ~47 分钟（与验证回测共享 CPU）。
  - 两 run 合计评估 **417/1440 个不同组合**（重叠 103）。
- 赢家固化：`research_ab/hptA_strategies/OPT9_HptWin.py`，显式子类（单值 default + optimize=False），
  命名 HptA_S1..S5（Sharpe 前 5 个**不同结果**——P2 惰性排列已合并）、HptA_C1..C5（Calmar）、HptA_BASE（冻结点回归哨兵）、
  HptA_D1/D2（单旋钮归因探针，非赢家）。
- **回归哨兵通过**：HptA_BASE 全窗回测 472 笔 / +2278.62% / DD 34.85%，与 lev_ARL_2x.zip 完全一致（子类 overlay 零行为漂移）。
- 口径披露：SharpeHyperOptLossDaily = 逐日利润桶（平仓日归属）年化 Sharpe（×√365），与回测报告的
  "Sharpe (daily wallet balance)"（含浮盈 MTM 的钱包余额日序列）**不是同一公式**——S1 IS 前者 1.865 / 后者 1.69。
  排序在各自口径内自洽；本报告比较表用报告口径，损失函数原值另行标注。CalmarHyperOptLoss = 报告口径
  "Calmar (closed trades)"（C1 IS 157.73 = 损失值 −157.7303，逐位复现）。

## 3. IS / 24-26 / 全窗对比（3 币，报告口径）

基线（HptA_BASE = ARL_2x）行加粗对照。SharpeD/CalmarD = 报告"Sharpe/Calmar (daily wallet balance)"。

### 3.1 Sharpe 赢家（S 系：全部 resample 3 / signal 2.25 / stop 2.25-3.0 / P2 惰性居多）

| 窗口 | 策略 | profit% | CAGR% | maxDD% | SharpeD | CalmarD | 笔数 |
|---|---|---|---|---|---|---|---|
| IS 21-23 | **BASE** | **1213.16** | **135.92** | **13.96** | **1.75** | **149.49** | **207** |
| IS | S1 (3/2.25/3.0/c3) | 424.86 | 73.79 | 13.50 | 1.69 | 55.15 | 140 |
| IS | S2 (3/2.25/2.5/c3) | 547.80 | 86.41 | 12.63 | 1.68 | 76.01 | 147 |
| IS | S3 (3/2.25/3.0/c2) | 418.74 | 73.11 | 13.50 | 1.67 | 54.34 | 138 |
| IS | S4 (3/2.25/2.5/c2) | 538.76 | 85.54 | 12.63 | 1.67 | 74.76 | 145 |
| IS | S5 (3/2.25/2.25/c3) | 677.19 | 98.08 | 12.06 | 1.67 | 98.44 | 153 |
| **24-26** | **BASE** | **88.02** | **26.39** | **34.84** | **0.80** | **4.94** | **264** |
| 24-26 | S1 | 95.28 | 28.18 | **13.90** | 1.01 | 11.48 | 174 |
| 24-26 | S2 | **125.87** | **35.29** | 18.96 | **1.07** | **11.12** | 178 |
| 24-26 | S3 | 95.28 | 28.18 | 13.90 | 1.01 | 11.48 | 174 |
| 24-26 | S4 | 125.87 | 35.29 | 18.96 | 1.07 | 11.12 | 178 |
| 24-26 | S5 | 124.20 | 34.92 | 19.15 | 1.03 | 10.52 | 181 |
| **全窗** | **BASE** | **2278.62** | **74.39** | **34.85** | **1.36** | 60.24 | **472** |
| 全窗 | S1 | 907.48 | 49.99 | **13.92** | 1.39 | 55.44 | 315 |
| 全窗 | S2 | 1340.27 | 59.69 | 18.98 | **1.41** | 59.53 | 326 |
| 全窗 | S5 | 1616.56 | 64.69 | 19.17 | 1.39 | **69.94** | 335 |

读法：S 系在 24-26 全面占优（利润、DD、SharpeD、CalmarD），但在 IS 大幅劣后（利润 −45%~−65%，报告口径 SharpeD 也不及）。
全窗利润仍不及基线，但 DD 腰斩、SharpeD/CalmarD 追平或反超。**这是一个"用 IS 利润换 24-26 平滑"的暴露收缩配置。**

### 3.2 Calmar 赢家（C 系：全部 resample 3 / signal 2.0=冻结 / stop 1.75-2.25）

| 窗口 | 策略 | profit% | maxDD% | SharpeD | CalmarD | 笔数 | IS Calmar(closed) |
|---|---|---|---|---|---|---|---|
| IS 21-23 | C1 (3/2.0/**1.75**/c3惰性) | **1291.73** | 14.29 | 1.62 | **155.19** | 226 | **157.73** |
| IS | C2 (…/1.75/c2) | 1267.57 | 14.29 | 1.61 | 152.28 | 223 | 154.78 |
| IS | C3 (…/2.0/c3：仅 P2 偏离) | 1233.97 | 13.96 | 1.76 | 152.05 | 210 | 154.22 |
| IS | C4 (…/2.25/c3) | 1027.67 | **11.66** | **1.78** | 152.45 | 205 | 153.83 |
| IS | C5 (…/2.25/c2) | 1015.33 | 11.66 | 1.78 | 150.62 | 203 | 151.98 |
| IS | **BASE** | 1213.16 | 13.96 | 1.75 | 149.49 | 207 | 151.63 |
| 24-26 | C1 | **126.72** | 34.89 | **0.93** | **7.10** | 268 | — |
| 24-26 | C2 | 130.25 | 34.90 | 0.95 | 7.29 | 266 | — |
| 24-26 | C3 | 87.27 | 34.81 | 0.80 | 4.90 | 265 | — |
| 24-26 | C4/C5 | ~81 | 32.0 | 0.81 | ~5.0 | ~260 | — |
| 24-26 | **BASE** | 88.02 | **34.84** | 0.80 | 4.94 | 264 | — |
| 全窗 | C1 | **2931.56** | 34.91 | 1.33 | **77.40** | 495 | — |
| 全窗 | C2 | 2925.94 | 34.91 | 1.33 | 77.25 | 490 | — |
| 全窗 | **BASE** | 2278.62 | **34.85** | **1.36** | 60.24 | 472 | — |

读法：C1/C2（stop 收窄到 1.75）三窗利润全 ≥ 基线（全窗 +28.6%），但 DD 不降（≈34.9%）、SharpeD 全窗略降；
C4/C5（stop 2.25）DD −3pp 但利润下降。**Calmar 面自己也在 stop 方向上分裂**（top-1 是 1.75，top-4/5 是 2.25）。

### 3.3 单旋钮归因（D 系，P2 全部冻结默认）

| 窗口 | 策略 | profit% | maxDD% | SharpeD | 笔数 |
|---|---|---|---|---|---|
| IS | BASE (2.0/2.0) | 1213.16 | 13.96 | 1.75 | 207 |
| IS | D1 (仅 signal→2.25) | 756.04 | 14.03 | 1.60 | 155 |
| IS | D2 (仅 stop→2.5) | 784.58 | 11.95 | 1.77 | 198 |
| 24-26 | BASE | 88.02 | 34.84 | 0.80 | 264 |
| 24-26 | **D1 (仅 signal→2.25)** | **122.28** | **23.70** | **0.96** | 185 |
| 24-26 | D2 (仅 stop→2.5) | 88.29 | 29.69 | 0.87 | 254 |
| 全窗 | D1 | 1786.74 | 23.72 | 1.33 | 341 |
| 全窗 | D2 | 1549.35 | 29.72 | 1.39 | 450 |

**归因结论：S 系的 24-26 利润增益几乎全部来自 signal 2.0→2.25（D1 单旋钮即得 122.3 vs 88.0），
stop 加宽主要贡献 DD 压缩（23.70→18.96）而不加利润；而 signal 2.25 在 IS 单独使用是强负贡献（756 vs 1213）。
即：同一旋钮在两个 regime 下符号相反 —— 与 INFER 的 rank IC 为负完全一致。**

## 4. 参数高原检查（IS 面，不同组合口径）

top-20% = 按 IS 损失排序的前 20% 不同组合（Sharpe 49/247，Calmar 54/273）。

| 参数 | Sharpe top-20% | Calmar top-20% | 判读 |
|---|---|---|---|
| resample_hours | **3:100%**（全体分布 56% 在 3） | 3:72%，2:28%，4/6:0% | **强高台**：两目标一致锁定冻结值 3；2/4/6 均值损失明显差。孤峰无邻域但方向两目标一致且是冻结值本身 |
| signal_atr_mult | 2.25:69%，2.0:31%，其余 0 | **2.0:72%**，2.25:11%，2.5:18% | 高台 {2.0, 2.25} 跨两目标共享；冻结值 2.0 在 Calmar 顶、在 Sharpe 面居次 |
| stop_atr_mult | 2.5:43%，3.0:24%，2.25:22%，2.0:10% | 2.0:33%，2.25:31%，1.75:19%，2.5:17%，3.0:0% | **方向分裂**：Sharpe 求宽、Calmar 求窄；均值面在 1.75-2.5 间平坦（Sharpe 面差值 ≤0.05） |
| cluster_stop_count | 3:57%（惰性） | 3:56%（惰性） | 见 §6：3 币下近乎不触发，平坦≠默认最优 |
| cluster_window_h | 24/48 ≈ 均分 | 24/48 ≈ 均分 | 惰性 |
| circuit_hours | 24/48/72 均分 | 48:44% 余均分 | 惰性 |

交叉表（均值损失，resample×signal，Calmar 面）：冻结入口格 (3, 2.0) = **−133.6**，是整个 4×5 入口网格中最优格；
次优 (2, 2.5)=−115.3、(3, 2.25)=−84.9。Sharpe 面最优格 (3, 2.25)=−1.695 vs (3, 2.0)=−1.688 —— 差 0.4%。
**入口几何的"高台中心"两目标都包含或紧邻冻结点。**

## 5. 多重检验披露

- 本次试验数：534 次 epoch 回测（Sharpe 254 + Calmar 279 + 冒烟 1），417 个不同参数组合（占网格 29%）。
  叠加 INFER 记载的 ~787 次家族历史试验 + OPT9/lev 消融 ~20 次，**家族总数 ~1340**。
- top-1 对冻结点的 IS 边际：Sharpe −5.60%（1.865 vs 1.766）、Calmar −4.02%（157.73 vs 151.63）。
- 高台带宽：Sharpe 面距 top-1 5% 以内有 **44 个**组合、2% 以内 30 个；Calmar 面 5% 以内 32 个、2% 以内 9 个。
  冻结点在两面上都落在距 top-1 5% 的带内（Sharpe 排名 49/247，Calmar 6/273）。
- 判读：从数十个彼此差距 ≤2-5% 的近并列组合中挑出的 top-1，其对带内任一成员（含冻结点）的边际就是
  best-of-N 期望膨胀的量级；且两个损失函数的 top 方向互相矛盾（§4）。**不构成显著超越。**
- 24-26 窗的 S 系优势未参与选择，形式上是"样本外"，但其规模（SharpeD +34% 相对）需对照分年不稳健性（§7）与
  拨盘语义折扣：它等价于"在 21-23 放弃一半利润，换取 24-26 少亏、少回撤"。若该权衡本身有价值，正确的讨论位置是
  风险预算/组合层（与 B sleeve、回收系数联动），不是参数层。

## 6. P2 熔断参数的发现（重要副产物 + 覆盖度限制）

- cluster_stop_count=3 时，IS 窗 6 种 (window, circuit) 排列产生**完全相同**的结果（熔断从未绑定）；
  count=2 与 count=3 全窗仅差 ~3 笔（BASE 472 vs C3 476）。
- 结论：**3 币宇宙上 P2 近乎不绑定**（同向止损簇稀疏）。OPT9 的 P2 取证与验证基于 12 币宇宙，不能由本次
  平坦面推断"P2 默认值在 3 币下最优/最差"——这是本网格的覆盖度限制，已如实披露。
  （副产品：这也解释了为何 top 组合偏爱 count=3——它把 P2 退化为 no-op，属于搜索空间退化，不是"更弱熔断更好"的证据。）

## 7. 证伪对照与分段稳健性

任务书要求的检查，逐条：

1. **最优 stop_atr_mult 偏离 2.0 且增益是否集中于单一年？**
   - C1（1.75）：分年利润增益 pp（C1−BASE）：2021 +2.3 / 2022 +1.0 / 2023 +12.0 / **2024 +17.6** / 2025 +4.4 / 2026p +3.1。
     六年全为正（对数贡献口径：24-26 增益的 ~65% 来自 2024；IS 增益的 ~80% 来自 2023）。部分命中"单年来源"警示。
   - S2（2.5）：分年相对差：2021 −36% / 2022 −58% / 2023 −12% / 2024 +69% / **2025 −64%** / 2026p +415%。
     剧烈翻转，**不稳健**。
2. **极窄止损≈高频砍单重犯？** C1 stop=1.75（网格内邻格，非极值；1.5 才是极值且 IS 均值显著更差）。
   笔数仅 +5~9%（全窗 495 vs 472），无砍单形态。**不构成重犯**，但注意它同时是名义放大拨盘（§0 结论 2）。
3. **盈利地板重犯？** 所有变体 be_floor=False 继承，无地板机制。S 系的 DD 压缩来自入场更少+名义更小，不是止盈结构。**无重犯。**
4. **冻结点自身地位**：Sharpe 面 49/247（恰为 top-20% 边界）、Calmar 面 6/273。冻结点不是孤峰、也不在谷底。

## 8. 复现命令

```bash
cd /d/Code/AIQuant/freqtrade-futures-lab
FT=.venv/Scripts/freqtrade.exe

# 1) 主 hyperopt（IS-only；每个损失函数一遍；~35-45 min each @ -j 8）
$FT hyperopt --userdir user_data --config user_data/configs/OPT7_config_12p.json \
  --strategy-path user_data/strategies/oss --strategy OPT9_Hpt \
  --timerange 20210101-20240101 -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
  --spaces buy sell --hyperopt-loss SharpeHyperOptLossDaily \
  --epochs 300 --random-state 42 --analyze-per-epoch -j 8 --disable-param-export \
  --logfile research_ab/logs/hptA_sharpe.log
# 结果: research_ab/results/hyperopt_A_sharpe.fthypt；Calmar 同式换 --hyperopt-loss CalmarHyperOptLoss
#      → research_ab/results/hyperopt_A_calmar.fthypt

# 2) 赢家验证（显式固化类；--strategy-list 需显式 --timeframe 1h）
$FT backtesting --userdir user_data --config user_data/configs/OPT7_config_12p.json \
  --strategy-path research_ab/hptA_strategies \
  --strategy-list HptA_BASE HptA_S1 HptA_S2 HptA_S3 HptA_S4 HptA_S5 --timeframe 1h \
  --timerange 20240102-20260912 -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
  --export trades --cache none --logfile research_ab/logs/hptA_val_sharpe_2426.log
# 同式：IS=20210101-20240101，FULL=20210101-20260912；C 系/D 系换名单

# 3) 高原聚合
.venv/Scripts/python.exe -I research_ab/scripts/hptA_plateau.py sharpe research_ab/results/hyperopt_A_sharpe.fthypt
```

## 9. 文件清单（结果隔离）

- 新策略：`user_data/strategies/oss/OPT9_Hpt.py`（任务书授权的新文件；未改任何已跟踪文件）
- 赢家固化：`research_ab/hptA_strategies/OPT9_HptWin.py`（BASE/S1-S5/C1-C5/D1-D2）
- hyperopt 结果：`research_ab/results/hyperopt_A_{smoke,sharpe,calmar}.fthypt`、`hptA_epochs_{sharpe,calmar}.csv`
- 验证回测：`research_ab/results/hptA_val_sharpe_{IS,2426,FULL}.zip`、`hptA_val_calmar_{IS,2426,FULL}.zip`、
  `hptA_year_y2021..y2026p.zip`、基线 `hptA_base_ARL2x_{IS,2426}.zip`
- 日志：`research_ab/logs/hptA_*.log|*.console.log`；脚本：`research_ab/scripts/hptA_{plateau,extract}.py`

## 10. 诚实披露（口径/近似/选择效应）

1. 本报告所有"赢家"均出自 534 次试验的选择；§5 的折扣是必要阅读，不是脚注。
2. Sharpe 损失与报告 SharpeD 口径不同（§2）；比较表统一用报告口径，损失原值在表中单独标注。
3. 24-26 与全窗回测含 2026-09-12 前的未平仓强平（force_exit）1 笔（基线口径，与既有结果一致）。
4. 年度切窗独立回测的年度利润连乘 ≠ 全窗利润（复利路径不同）；分年表只用于归因方向，不用于精确分解。
5. P2 参数在 3 币上近乎不绑定（§6）——P2 结论限于"本网格无法评估"，未对 OPT9 的 12 币 P2 结论提出任何修改。
6. 冒烟/主 run 均以 --disable-param-export 运行，未在 user_data/strategies 下落任何参数文件；
   user_data/hyperopt_results 仅余 freqtrade 内部 tickerdata pickle（可再生缓存）。
7. 单 epoch 43s（-j 1）测量自冒烟；预算判定"300×2 epochs ≈ 60-80 分钟"与实测（33+47 分钟）一致。
8. **工作区事件披露（已修复）**：验证回测前两次启动失败（CategoricalParameter 单值校验、--strategy-list 需显式
   --timeframe），失败后脚本中的"移动最新 zip"步骤仍执行，误移了 user_data/backtest_results 里的旧文件：
   其中 2 个**已跟踪** zip（backtest-result-2026-09-11_15-43-23.zip、2026-09-12_00-54-07.zip）与已跟踪的
   user_data/hyperopt.lock（freqtrade hyperopt 正常退出时自动删除锁文件所致）——三者均已用
   `git checkout -- <file>` 从索引恢复，`git status` 确认已无任何已跟踪文件改动/删除（无 commit/push）。
   另有 3 个未跟踪 zip（2026-11-04_01-20-40/01-22-17/01-26-48，时间戳与 research_ab/results/lev_*.zip
   归档一一对应，为重复副本）被误移后清理，内容已在 research_ab/results 保留，无结果损失。
   后续脚本已修正为仅移动本次运行新生成的 zip。
