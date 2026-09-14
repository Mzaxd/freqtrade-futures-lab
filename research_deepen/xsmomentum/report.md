# XS-Momentum Sleeve 立项研究：GO/NO-GO 报告

**判定：NO-GO**（预注册判据 3 失败：VAL 2023 LS Sharpe = −0.43，要求 > 0.5）

- 结论级别：**[假设生成]**（IS/VAL 均为烧毁窗口上的探索；验证级结论只能来自未来数据）
- 日期：2026-09-14；沙盒：`research_deepen/xsmomentum/`
- 预注册文件（一切结果计算之前写死）：`research_deepen/xsmomentum/PREREGISTRATION.md`

---

## 1. 判定一览（预注册四判据）

| # | 判据（PREREG §5） | 实测 | 通过？ |
|---|---|---|---|
| 1 | IS 高原成立（≥5 格）且高原 Sharpe 中位数 > 0 | 5 格（恰好踩线），中位 Sharpe 1.154 | 通过（勉强） |
| 2 | 选中参数 IS(2021-22) LS 净 Sharpe > 0 | **+1.04**（净收益 +211%，DD −63%） | 通过 |
| 3 | VAL 2023 LS 净 Sharpe > 0.5 | **−0.43**（净收益 −23.6%，DD −50.7%） | **失败** |
| 4 | 与 Sleeve A 月度收益相关性 < 0.3（2021-2023, 36 个月） | Pearson **0.016**（Spearman 0.10） | 通过 |

**四条须同时成立 → NO-GO。** 核心死因：多头-空头对冲版在 2023 年一次性验证中亏损，
空头腿（做空 2022 年输家）在 2023 复苏年被碾压——典型横截面动量的"空头腿动量崩溃"。

## 2. 方法

### 2.1 宇宙（预注册 v2，见 PREREGISTRATION.md 修订记录）

- 候选：Binance USDT-M 线性永续中当前仍上市、非稳定基币、首根 1d K 线 ≤ 2021-12-31 者，共 89 个。
- 排序：**2021-01-01→2023-12-31 窗口内 1d 名义成交额（close×volume）中位数**降序，取前 40 冻结
  （流动性排序，性能盲；名单：`universe_frozen_v2.md`，12 老币全部入选）。
- 预注册 v1（按 2026-09-14 当日 24h 成交额快照 top-40）在下载任何数据之前被弃用：
  该快照含大量 2024-2026 上市合约（SKHYNIX、XAU、龙虾等），严格执行会使 IS 期合格币仅剩 ~15 个，
  与"多币全市场"研究意图结构性冲突。修订发生在任何回测/收益计算之前，全程留档
  （`universe_v1_2026snapshot_DISCARDED.json`）。

### 2.2 独立研究引擎（`scripts/xs_engine.py`，纯 pandas/numpy）

- 信号：mom = close[t−skip]/close[t−skip−lookback] − 1；lookback ∈ {7,14,30,60,90}，skip ∈ {0,1}。
- 组合：合格币（动量窗口数据完整）按动量降序，top/bottom 各 ceil(0.2N) 名；LS/LO/SO 三版，
  持有 H ∈ {1,5,10} 日，组内等权，LS 两腿各 100% 名义（gross 2.0）。
- 成本：taker **0.1%/边**（往返 0.2%，为 Binance 实际 0.05% 的 2 倍保守），对再平衡日单边换手名义计费；
  funding 按 8h 结算事件逐日记入持仓方向（正费率多头支付/空头收取；40 币 funding 全部可得，无按 0 填充者）。
- 防前视：信号 t 日收盘可知 → t 日收盘调仓、t→t+1 起算收益；持有期权重随价格漂移（自融资语义）；
  合成数据单测验证（未来数据篡改不影响历史收益，max|diff|=0）。
- 可交易门槛（合格币 <10 空仓）从未触发（IS/VAL 全程 n_flat_days=0；合格币中位数 39/40）。

### 2.3 纪律执行

- IS 2021-01-01→2022-12-31 跑全网格（30 参数组 × 3 组合版）→ 高原分析 → 机械选中参数；
- 高原规则：LS IS Sharpe ≥ 0.8×全网格最大（阈值 1.0345）且 > 0；高原 = **5 格**
  （lb7/14/30 × sk0 × h1/10 交叉处），坐标中位数 (14, 0, 10) 恰为高原成员 → 选中 **lb14/sk0/h10**；
- VAL 2023 **只跑了这一次**（选中参数），无任何换参重跑。

## 3. 关键数字

### 3.1 IS 2021-2022（全网格 LS Sharpe，净成本后）

| lookback \ (skip,hold) | (0,1) | (0,5) | (0,10) | (1,1) | (1,5) | (1,10) |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | 0.92 | 0.77 | **1.15** | 0.34 | 0.30 | 0.50 |
| 14 | **1.15** | 0.58 | **1.04** ←选中 | 0.39 | 0.99 | 0.90 |
| 30 | **1.28** | **1.03** | **1.29** | 0.75 | 0.65 | 0.65 |
| 60 | −0.35 | −0.48 | 0.00 | −0.54 | −0.34 | −0.38 |
| 90 | 0.49 | 0.00 | 0.12 | −0.02 | −0.10 | 0.06 |

（粗体 = 高原成员；高原 = Sharpe ≥ 1.0345；全网格最大 lb30/sk0/h10 = 1.29，+388%，DD −57%）

- 高原结构：短 lookback（7-30 天）× skip 0 集中；60/90 天长动量在加密横截面上失效（与股票市场 12 月动量截然不同）。
- 边界敏感性披露：lb30/sk0/h5 的 Sharpe 1.0277 距高原线 1.0345 仅差 0.007，高原格数 5 恰好踩在成立门槛上——高原"成立"本身不稳健。

### 3.2 选中参数（lb14, sk0, h10）明细

| 窗口 | 组合 | 总收益 | 年化波动 | Sharpe | MaxDD | PF | 胜率(日) | 费用合计 | funding 合计 | 单次再平衡换手 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| IS 2021-22 | LS | +211% | 103% | **+1.04** | −63% | 1.22 | 51.5% | 0.208 | +0.003 | 2.84 |
| VAL 2023 | LS | **−23.6%** | 42% | **−0.43** | −50.7% | 0.94 | 49.3% | 0.103 | +0.019 | 2.78 |
| VAL 2023 | LO（披露） | +100.9% | 67% | +1.37 | −50.4% | 1.22 | 53.4% | 0.047 | −0.039 | 1.26 |
| VAL 2023 | SO（披露） | −75.3% | 66% | **−1.77** | −76.6% | 0.77 | 44.1% | 0.057 | +0.065 | 1.53 |

### 3.3 失败机制诊断

- **空头腿在 IS 就已全面失败**：SO 版 30/30 格 IS Sharpe 全为负（最好 −0.14）。
  LS 的 IS 盈利 = 强多头腿动量 − 空头腿拖累；该结构在 2023 复苏年反转。
- 2023 逐月：1 月市场（宇宙等权）+59%、LS −14%；2 月 LS −33%（空头腿动量崩溃）；H2 企稳但全年 −23.6%。
- LO 的 2023 +101% 是 beta 而非 alpha：LO 与市场月收益相关 **0.74**；LS 与市场仅 0.18。
- funding 对 LS 近似中性（两腿方向相反），费用是主要摩擦（IS 费用 0.208 ≈ 权益的 21%）。

### 3.4 与 Sleeve A（OPT4）的组合价值

- XS_OPT4Ref（原封 OPT4_VolatilitySystem + OPT7_config_12p.json，12 币 MOT4）重跑 2021-2023
  复现冻结档案：+1464.1%，Sharpe 1.01，436 笔（zip：`results/xs_opt4ref_2021_2023.zip`）。
- 月度收益相关性（36 个月）：**Pearson 0.016 / Spearman 0.10** → 相关性判据通过。
  若未来该家族被改良到可上线，分散价值确实存在；但当前版本收益为负，相关性再低也无意义。

## 4. 局限与诚实披露

1. **幸存者偏差**：候选集只含 2026-09 仍上市的合约（89 个），2021-2023 间下架币缺席。
   对 LS 的方向性影响不确定：多头腿偏赢家（高估），空头腿缺失已死币（其空头本可能获利 → 低估）。
2. **宇宙排序的后视成分**：按 2021-2023 窗口内成交额排序，偏好该窗口交易火热的幸存者；
   但排序变量是流动性而非收益，且冻结先于一切收益计算。
3. **成本近似**：无滑点/冲击成本（0.1%/边已含 2 倍缓冲）；funding 按日聚合计入当日持仓
   （8h 事件与日结算的时序近似）；无借贷成本；LS gross 2.0 未建模保证金占用与强平风险。
4. **VAL 是单年单次**：2023 是低波动复苏年，对空头腿最不利的单一情景；判据失败可能部分是
   "年份 unlucky"。但预注册规则就是如此设计的——一次性 VAL 不过关即 no-go，不允许"再看一年"。
5. 高原格数恰踩 5 格门槛（§3.1 边界敏感性），高原本身不稳健。
6. LO 版 IS 30/30 格为正、VAL +101%，但 LO=动量 beta（与市场相关 0.74），与 Sleeve A 同源风险，
   且 IS +912%/DD −83% 的形态无独立配置价值；预注册已规定 LO/SO 不参与判定。
7. 检查无误项：40 币 funding 数据完整（无按 0 填充）；NaN 均为上市前；空仓门槛从未触发；
   引擎防前视单测通过；VAL 只跑一次；一切评估 ≤ 2023-12-31。

## 5. 结论 [假设生成]

1. **NO-GO**：横截面动量排序（top/bottom 五分位多空，40 币全市场）在预注册纪律下未通过
   一次性 2023 验证（LS Sharpe −0.43 vs 线 0.5）。失败机制明确：**空头腿结构性亏损**
   （IS 30/30 格为负）+ 2023 复苏年空头腿动量崩溃。
2. 正向遗产：短 lookback（7-30 天）× skip0 的 IS 高原真实存在（Sharpe 1.0-1.3）；
   与 Sleeve A 相关性 0.016 → 该收益源家族与现有单策略趋势 sleeve 正交，**家族方向不必整体关闭**。
3. 若未来重启（须新数据、新预注册），证据指向：**只做多头的短周期横截面动量 + 已有趋势 sleeve**
   的组合（LO 的市场暴露可由 A 的空头腿对冲），或动量排序做仓位倾斜而非独立做空腿。
   本次不做任何此类变体的 VAL（纪律禁止）。

## 6. 复现命令（裸仓库 → 本报告）

```bash
cd /d/Code/AIQuant/freqtrade-futures-lab
# 1) 候选与冻结宇宙（预注册规则先于下载写死）
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/select_candidates.py   # 89 候选 -> candidates.json
# 2) 下载数据（私有 userdir，timerange 截止 20240101）
.venv/Scripts/freqtrade.exe download-data --userdir research_deepen/xsmomentum/userdir \
  --config research_deepen/xsmomentum/configs/download_candidates_1d.json \
  --timeframes 1d --timerange 20200101-20240101        # 自动附带 1h funding_rate+mark，267 文件
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/freeze_universe_v2.py   # 冻结 top-40
# 3) IS 全网格 + 高原选择 + 一次性 VAL
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/xs_engine.py is         # grid_is.csv
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/plateau_select.py       # lb14/sk0/h10
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/xs_engine.py val 14 0 10 # 只此一次
# 4) 诊断与 Sleeve A 相关性
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/diagnose.py
.venv/Scripts/freqtrade.exe backtesting --userdir user_data --config user_data/configs/OPT7_config_12p.json \
  --strategy-path research_deepen/xsmomentum/strategies --strategy XS_OPT4Ref \
  --timerange 20210101-20240101 --export trades --cache none    # zip 已归档 results/xs_opt4ref_2021_2023.zip
.venv/Scripts/python.exe research_deepen/xsmomentum/scripts/corr_sleeveA.py
```

产物索引：`results/grid_is.csv`（30×3 全指标）、`results/daily_is.csv|daily_val.csv`（日收益）、
`results/plateau_selection.json`、`results/corr_sleeveA.json`、`results/diagnostics.json`、
`results/monthly_table.csv`、`results/xs_opt4ref_2021_2023.zip`、`universe_frozen_v2.{json,md}`。

> 不构成投资建议。无稳定盈利保证。未连接实盘。
