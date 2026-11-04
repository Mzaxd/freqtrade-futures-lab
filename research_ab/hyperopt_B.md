# Hyperopt-B — sleeve B（OPT2_MomRegime15mLb21）可识别参数超参实验

日期 2026-11-04 · 工作区 research_ab · 3 币宇宙 BTC/ETH/SOL（Binance USDT-M 永续，15m）
窗口纪律：**优化仅用 IS 20210101-20240101；20240102-20260912 为披露窗，未参与任何选择**。

## 0. 结论先行（以 24-26 披露窗为准）

**无可显著超越冻结基线的参数组合。** 两个损失函数（Sharpe-HyperOpt-Loss-Daily /
Calmar-Hyper-Opt-Loss 同口径复刻）在 IS 上各自选出的赢家，放到 24-26 披露窗：

| 策略（MTM 口径，全窗 zip 切片） | IS ret | IS maxDD | IS Sharpe | **24-26 ret** | **24-26 maxDD** | **24-26 Sharpe** | 全窗 ret | 全窗 maxDD | 全窗 Sharpe | 笔数(全窗) |
|---|---|---|---|---|---|---|---|---|---|---|
| 冻结基线 (100/50/-0.03/0.0005/0.45) | +2420% | -29.3% | 2.24 | **+57.7%** | **-27.2%** | **0.67** | +4076% | -29.3% | 1.66 | 135 |
| WB_SHARPE（仅 PER_COIN_SMA=20） | +1549% | -22.9% | 2.17 | **+65.3%** | **-25.9%** | **0.77** | +2723% | -25.9% | 1.64 | 199 |
| WB_CALMAR（tol=-0.02 + MPW=0.60） | +3490% | -32.8% | 2.32 | **+61.8%** | **-27.1%** | **0.69** | +6018% | -32.8% | 1.72 | 136 |

- WB_SHARPE 在 24-26 三项指标小幅全面占优（+7.6pp 收益、DD 浅 1.3pp、Sharpe +0.10），但代价是
  IS/全窗利润被砍 ~35-40%（+2723% vs +4076%）——它是"用收益换平滑"，不是发现更好的策略。
- WB_CALMAR 的 IS Calmar 翻倍（-1058 vs -539）**没有**转化为 OOS 回撤改善：24-26 DD 与基线持平
  （-27.1% vs -27.2%），全窗 MTM DD 反而恶化到 -32.8%。freqtrade 闭口 Calmar（IS 闭口 DD 仅 5.7%）
  与 MTM 含浮亏口径严重背离，是 IS 假信号。
- 建议：**B 保持冻结基线不变**。PER_COIN_SMA 向短窗（20-30）移动是唯一方向一致（IS 与 24-26
  同向小幅改善 DD/Sharpe）的候选，但证据强度不足以推翻预注册参数，留待后续独立验证。

## 1. 结构性约束：3 币上排名参数不可识别（最重要）

B 的 docstring（OPT1_MomRegime15mLb21）自证：3 币宇宙上 TOP_N=3 使 `rank<=TOP_N` 对所有白名单
币恒真——横截面排名参数 **MOM_LOOKBACK_DAYS、EXIT_RANK_N、TOP_N 在 3 币上不可识别**（历史上
两个 lookback 变体逐字节相同）。部署宇宙即 3 币，故本实验**只搜索 3 币可识别参数**：

| 参数 | 网格 | 归属 space |
|---|---|---|
| REGIME_SMA（BTC 牛熊开关，日线根数） | {50,75,100,125,150} | buy |
| PER_COIN_SMA（持仓币自身日线过滤） | {20,30,50,75,100} | buy |
| REGIME_TOLERANCE（ron = btc>sma×(1-tol)） | {-0.03,-0.02,0,+0.02} | buy |
| funding_max（funding 闸门） | {0.0003,0.0005,0.0008,1.0} | buy |
| MAX_POSITION_WEIGHT（单仓权重上限） | {0.30,0.45,0.60} | sell |

网格 5×5×4×4×3=1200。偏离任务书的披露：tolerance 网格**加入 -0.03**（使冻结基线格点在网格内，
锚定可比性）；funding 的"None/无限"以 **1.0 哨兵**实现（opt_common.funding_gate_long 自身文档
推荐的做法，避免 None 参与数值比较）；QUOTE_VOLUME_HEADROOM_MULT 按任务书豁免未搜。

**12 币副实验（测排名参数）被砍掉**：实测 3 币单 epoch ≈ 2m13s（-j1、无竞争），12 币数据量 4 倍
起、且锁定/网络事故已耗掉一半预算（见 §3），无法在 2h 纪律内完成有意义的 epoch 数。口径差异
（缩短 IS 等）不再适用——未做，如实披露。12 币上 lb14 vs lb21 的可识别性此前已在 OPT1 阶段验证过
（12 币结果不同），本实验无新增证据。

## 2. 实验执行与诚信披露（时间线与方法变更）

按任务书先冒烟、后定预算，实际遭遇四起事故，方法随之一次转向，全程记录：

1. **冒烟（成功）**：`OPT2_Hpt`（新文件 user_data/strategies/oss/OPT2_Hpt.py，任务书明示路径）把
   上述参数声明为 freqtrade Parameter。freqtrade 2026.8 的 Parameter 需 `.value` 访问而父类经
   `self.XXX` 读**类属性**（已跟踪文件不可改）——解法：Parameter 用新名（regime_sma 等）+
   父名只读 property 转发 `.value`。冒烟确认：参数表被识别（epoch 记录 `params_dict` 五参数齐）、
   **position_adjustment 正常执行**（基线 IS 64 笔含 388 张订单，每笔 ≥2 次入场、最多 32 次分批
   减仓；hyperopt epoch1 同窗口 80 笔同量级）、单 epoch 2m13s。
2. **并行 agent 锁冲突**：main userdir 的 hyperopt.lock 被同仓库另一 agent 的 OPT9_Hpt hyperopt
   持有（未动它）→ 本实验改用**隔离 userdir** research_ab/hptB_userdir(_calmar)（15m/funding/mark
   feathers 拷贝，符合结果隔离纪律）。
3. **dapi.binance.com 中断**：ccxt loadMarkets 会拉 delivery API，当日不可达 → 加
   research_ab/hptB_config_overlay.json（fetchMarkets 仅 spot+linear；纯连通性绕过，不影响回测数学）。
4. **loky worker 病态**：`-j 4` 时 worker 单 epoch >18 分钟不返回（主进程同 cell 2m13s）→ 改
   `-j 1`。随后又遇 **freqtrade 2026.8 默认 NSGAIIISampler 且 INITIAL_POINTS=30**（30 个纯随机
   启动点 > 全部预算）→ 嵌套 HyperOpt 类改 **TPESampler(seed=42, n_startup_trials=6)**（偏离
   默认的披露：单目标损失下 NSGA-III 是浪费，TPE 是经典单目标选择）。
5. **TPE 运行仍停滞**：两损失各完成 3 epochs 后，第 4 个 cell（两 run 同 seed 采样同一序列）
   进入 30+ 分钟不返回——持仓近乎常开的 cell 触发每 candle×3 持仓的
   adjust_trade_position 风暴（每回调重算 _portfolio_value）。终止两 run，存档 6 个 epoch 记录
   （research_ab/results/hptB_{sharpe,calmar}_epochs.fthypt，3 个唯一 cell）。
6. **方法转向（Plan B）**：改为**预注册 one-at-a-time mini-grid**——锚点=冻结基线，16 个 cell
   每次只动一维（research_ab/strategies/hptB_cells.py，跑前写死），直接 IS 回测，损失用与
   freqtrade **逐行同口径**的复刻公式从 trades 计算（SharpeDaily：日汇总 profit_ratio-0.0005
   滑点×√365；Calmar：freqtrade.data.metrics.calculate_calmar）。15/16 完成；M30（MPW=0.30）
   25 分钟超时、45 分钟重试仍超时——0.30 上限低于等权 1/3 目标导致永久 trim 风暴，**该 cell
   运行时间本身即操作性否决**，记 DNF。
7. 交互 cell X1（P20+M60）、X2（Tm02+M60）为**事后**选择（看到主效应后加，选择效应在此披露）。

## 3. IS 迷你网格全表（主效应）

CSV：research_ab/results/hptB_grid_losses.csv。按 Sharpe 损失排序（越负越好）；基线行加粗参照。

| cell | 变更 | 笔数 | 利润% | ftDD% | Sharpe损失 | Calmar损失 | MTM ret% | MTM DD% | MTM Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| P20 | PER_COIN_SMA=20 | 105 | 1538.7 | 19.0 | **-1.451** | -144.3 | 1548.8 | -22.9 | 2.17 |
| X1 | P20+MPW0.60（事后） | 105 | 1827.9 | 19.0 | -1.398 | -171.5 | 1839.9 | -24.1 | 2.17 |
| P30 | PER_COIN_SMA=30 | 86 | 1830.4 | 17.5 | -1.173 | -186.0 | 1843.1 | -28.9 | 2.16 |
| R50 | REGIME_SMA=50 | 80 | 1859.4 | 26.8 | -1.089 | -121.2 | 1872.7 | -36.2 | 2.12 |
| **baseline** | — | 64 | 2403.6 | 7.8 | **-0.954** | **-539.4** | 2421.3 | -29.3 | 2.25 |
| F10 | gate off(1.0) | 64 | 2483.8 | 7.8 | -0.952 | -557.4 | 2502.0 | -28.7 | 2.26 |
| Tm02 | tol=-0.02 | 65 | 2369.5 | 5.7 | -0.951 | -722.3 | 2386.9 | -29.3 | 2.23 |
| R75 | REGIME_SMA=75 | 80 | 1649.0 | 37.5 | -0.942 | -76.9 | 1661.3 | -47.7 | 2.02 |
| F03 | funding 0.0003 | 63 | 2508.0 | 7.8 | -0.941 | -562.8 | 2514.3 | -29.1 | 2.27 |
| F08 | funding 0.0008 | 64 | 2478.7 | 7.8 | -0.919 | -556.2 | 2497.0 | -29.1 | 2.26 |
| T0 | tol=0 | 67 | 2225.6 | 21.9 | -0.912 | -178.2 | 2242.1 | -38.9 | 2.17 |
| R125 | REGIME_SMA=125 | 61 | 2096.5 | 21.8 | -0.885 | -168.4 | 2112.1 | -28.8 | 2.17 |
| M60 | MPW=0.60 | 64 | 3523.0 | 7.8 | -0.872 | -790.6 | 3548.6 | -32.8 | 2.33 |
| X2 | Tm02+M60（事后） | 65 | 3467.7 | 5.7 | -0.870 | **-1057.6** | 3493.0 | -32.8 | 2.32 |
| Tp02 | tol=+0.02 | 85 | 1810.7 | 36.2 | -0.866 | -87.5 | 1824.2 | -49.8 | 2.03 |
| P75 | PER_COIN_SMA=75 | 67 | 2116.5 | 12.1 | -0.865 | -340.1 | 2132.6 | -30.5 | 2.12 |
| R150 | REGIME_SMA=150 | 56 | 1704.3 | 13.6 | -0.835 | -218.7 | 1717.1 | -28.0 | 2.10 |
| P100 | PER_COIN_SMA=100 | 62 | 1606.6 | 15.2 | -0.828 | -185.2 | 1612.3 | -32.6 | 1.98 |
| M30 | MPW=0.30 | — | — | — | **DNF**（25/45min 超时） | — | — | — | — |
| hptS_ep2 | 150/20/-0.03/off/0.60 | 105 | 1057.3 | 22.4 | -1.321 | -82.4 | （hyperopt 存档 cell） | | |

（hptS_ep1/ep3、hptC_ep1-3 为 hyperopt 存档的另 2 个唯一 cell：(100/75/+0.02/0.0005/0.6)
Sharpe -0.762/Calmar -111.8；(75/100/+0.02/0.0005/0.6) Sharpe -0.744/Calmar -49.4。）

**主效应读法（高原分析替代——OAT 网格给出轴向响应面，联合面仅 6 个交互点散样）：**

- **REGIME_SMA**：100 不是孤峰——125/150 的 MTM DD 相若（-28.x%），50/75 显著更差（-36/-48%）；
  Sharpe 上 50 略好（-1.089）但以 DD 恶化 7pp 为代价，且见 §5 偷看检验。**牛熊开关窗口在
  100 附近是宽平台**，无过拟合孤峰。
- **PER_COIN_SMA**：20-30 降 DD（-22.9/-28.9）也降利润（-1549/-1843）；75/100 双向变差。
  50 居中，20 是唯一 IS+OOS 方向一致的微改善方向。
- **REGIME_TOLERANCE**：-0.03/-0.02 几乎同（预注册 -0.03 的稳健性佐证）；≥0 急剧恶化
  （tol=+0.02 → DD -49.8%）。**预注册值在平台左缘，安全。**
- **funding_max**：全维度近零效应（利润 2404→2508→2479→2484，DD 持平）。IS 内三币结算费率
  >0.0003/0.0005/0.0008 的占比仅 10.5-12.1%/6.2-7.5%/3.5-4.3%——闸门偶发触发但被阻塞的
  加仓随后即补足，**3 币上此旋钮经济上不敏感**。
- **MAX_POSITION_WEIGHT**：0.60 大幅增利（+3523%）但 MTM DD -32.8%（更差）；0.30 计算上
  不可行（trim 风暴）。0.45 是计算与风险的双重点。
- **Calmar 口径警示**：ftDD（闭口）与 MTM DD 排序严重背离（X2 闭口 5.7% vs MTM -32.8%），
  闭口 Calmar 最大化会系统性选高浮亏容忍 cell。

## 4. 三段验证（正式回测，MTM 口径）

主表见 §0（全窗 zip 切片，交易连续）。独立分段回测交叉核对（窗口起点 20240102，跨窗交易
归因差异 ≤1.5pp）：

| 独立回测 | 24-26 ret | 24-26 maxDD | 24-26 Sharpe |
|---|---|---|---|
| baseline | +59.5% | -27.2% | 0.69 |
| WB_SHARPE | +66.8% | -25.9% | 0.78 |
| WB_CALMAR | +69.2% | -27.1% | 0.75 |

选择效应量化：IS 上 18 cell 的 Sharpe 损失极差 0.62（-0.828..-1.451），赢家 IS 优势 -0.50，
到 24-26 收缩为 Sharpe +0.10 / ret +7.6pp——**符合"max-statistic 选择偏差在 OOS 衰减"的形态**，
不足以宣称真实改善。

## 5. REGIME_SMA 偷看检验（B 独有）

问题：最优 REGIME_SMA 相对 100 的偏移是否只是把 2022 熊市进出时点挪得更准（IS 内偷看周期）？
取网格内 Sharpe 最优的 regime cell **R50（SMA50, tol=-0.03）** vs 基线 SMA100，用策略自身
因果语义（昨收 vs 昨收 SMA）逐日对齐信号（脚本 research_ab/scripts/hptB_regime_peek.py，
图 research_ab/results/hptB_regime_peek_sma50.png）：

| 分歧日类型 | IS 21-23 | 24-26 |
|---|---|---|
| 基线 ON、SMA50 OFF（避开暴露） | 149 天，次日 BTC 均值 **-0.330%/天**（累计 **-43.2%**） | 132 天，次日 **+0.113%/天**（累计 **+13.1%**） |
| SMA50 ON、基线 OFF（增加暴露） | 100 天，次日 +0.108%/天（累计 +5.1%） | 42 天，次日 **-0.280%/天**（累计 **-12.1%**） |

**答案：是。** SMA50 的 IS Sharpe 增益本质上是在 2021-22 回避了 -43% 累计漂移的下跌日（另加
+5% 的错位收益）；同样形态的分歧日在 24-26 反向（避开的日子上涨 +13%、追加的日子下跌 -12%，
净相对拖累约 -25pp）。R50 的 IS 优势是周期位置偷看，不具 OOS 生命力——REGIME_SMA 维持 100。
年度风险 ON 天数（基线）：2021 246 / 2022 15 / 2023 239 / 2024 246 / 2025 170 / 2026(至9月) 61。

## 6. 复现命令

```bash
# 环境：.venv（freqtrade 2026.8）；隔离 userdir（15m+funding+mark feathers 已拷贝）
# PYTHONPATH 仅为多进程 worker 导入策略目录（-j1 非必需，保留无害）
UD=research_ab/hptB_userdir
CFG=(-c user_data/configs/OPT7_config_12p.json -c research_ab/hptB_config_overlay.json)

# hyperopt（存档：3+3 epochs 后因慢 cell 终止）
PYTHONPATH=user_data/strategies/oss .venv/Scripts/freqtrade.exe hyperopt \
  --userdir $UD "${CFG[@]}" --strategy-path user_data/strategies/oss \
  --strategy OPT2_Hpt --timerange 20210101-20240101 \
  -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \
  --spaces buy sell --analyze-per-epoch --random-state 42 -j 1 --min-trades 20 \
  --disable-param-export --hyperopt-loss SharpeHyperOptLossDaily   # 或 CalmarHyperOptLoss
# 注：OPT2_Hpt 内嵌 HyperOpt 类强制 TPESampler(seed, n_startup_trials=6)

# 迷你网格 + 交互 cell（冻结类：research_ab/strategies/hptB_{cells,winners}.py）
bash research_ab/scripts/hptB_run_cells.sh        # 16 cell，3 流并发，单 cell 25min 上限
.venv/Scripts/python.exe -I research_ab/scripts/hptB_grid_losses.py   # 双损失+MTM 汇总

# 冻结赢家三段回测（--strategy WB_SHARPE|WB_CALMAR，--timerange 见下）
#   IS 20210101-20240101 · 24-26 20240102-20260912 · full 20210101-20260912
.venv/Scripts/python.exe -I research_ab/scripts/hptB_mtm_metrics.py <zip...>

# REGIME_SMA 偷看检验
.venv/Scripts/python.exe -I research_ab/scripts/hptB_regime_peek.py 50 -0.03 \
  research_ab/results/hptB_regime_peek_sma50.png
```

## 7. 口径与局限（诚实清单）

- 主口径 = MTM 日度权益（dp_mtm.py 逐时重建，与基线引用 +4076%/-29.3% 同源）；freqtrade 闭口
  口径另列。两口径在 DD 上量级不同（IS：闭口 7.8% vs MTM 29.3%），结论以 MTM 为准。
- hyperopt 损失（SharpeDaily/Calmar）本身基于闭口 trades——与最终 MTM 判据不同，X2 的"IS Calmar
  翻倍"正是该口径差的产物（§3 警示）。
- 预算实测：单 epoch 2m13s（-j1 无竞争）~4.5min（竞争）；含事故恢复全程超 2h 目标（约 3.5h），
  hyperopt 部分（TPE）只完成 6 epochs（3 唯一 cell），主证据来自 17-cell 预注册网格 + 2 事后
  交互 cell——**事后 cell 的选择效应已披露，交互面未穷举**。
- M30 cell DNF（计算不可行）使 MPW 下行方向无数据。
- 12 币排名参数副实验未做（§1）。funding 闸门 3 币不敏感的结论仅限 IS 窗口费率分布。
- 新增未跟踪文件：user_data/strategies/oss/OPT2_Hpt.py（任务书指定）、research_ab/{strategies,
  scripts, logs, results, hptB_userdir*, hptB_config_overlay.json}。未做任何 git 操作，未改任何
  已跟踪文件。
