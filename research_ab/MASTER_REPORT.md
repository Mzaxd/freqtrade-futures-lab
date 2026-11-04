# research_ab MASTER REPORT — AB + 动态调仓 + 3 币 路径总裁决

> **状态：🔒 已冻结（2026-11-04）。** 冻结范围：预注册包（§3：3 币宇宙 / A=OPT9_Recycle@1.21× 钱包70% / B=MomRegime 钱包30% MOT3 / 实盘门槛≥5,000 / 红线 -20%/30d + -25% 从峰 / G0-G6 gate）与全部研究结论（WS1-WS4 + 杠杆地图 + 双侧 hyperopt 终裁决）。后续任何修改 = 解冻 + 重新预注册。可再生日志/hyperopt 工件未入库（seed=42 可复现）。

> 调度：主会话 ｜ 执行：4 个并行 agent（WS1-WS4）＋调度员交叉核验 ｜ 2026-11-03
> 数据纪律：全部基于 3 币（BTC/ETH/SOL）窗口 20210101-20260912；OPT4 基 sleeve 曲线 + OPT9 回收变体实测。

## 1. 四工作流结论一览

| # | 问题 | 裁决 | 报告 |
|---|---|---|---|
| WS1 | 最小运行资金 | 数学门槛 ≈1,500；**严肃档（sizing 失真<10%）≈3,500，对 BTC 极价稳健取 5,000**；回收系数不改门槛 | [ws1_min_capital.md](ws1_min_capital.md) |
| WS2 | AB 比例 × 回收 × 形势 | **预注册 (wB=0.30, f=0.5)=70/30 半回收**：CAGR 81.7%/Sharpe 1.93/MC p95 30dDD -18.4%（余量1.6pp）/P(触线)1.8%；wB≥0.45 与 50/50 半/全回收被 MC 否决 | [ws2_weights_regimes.md](ws2_weights_regimes.md) |
| WS3 | 回收乘子实现 | **OPT9_Recycle 实现正确**：乘子=1 回归 472 笔逐笔一致；信号与 B 0 不匹配；lookahead no-bias；1.28/1.56 实测 CAGR +8.4/+15.8pp，但 1.56 单路径 30d 滚动 -19.3%（距红线 0.7pp）→ **1.56 双重否决**（WS2 MC + WS3 单路径同向） | [ws3_recycle_impl.md](ws3_recycle_impl.md) |
| WS4 | 部署蓝图 | 两容器 A/B、G0-G6 gate、风险登记册 12 条、live bug 6 条对策、季度再平衡 runbook | [ws4_deployment.md](ws4_deployment.md) |

## 2. 交叉一致性核验（调度员）

1. **乘子口径闭环**：WS2 推荐配置熊态 A 有效权重 0.85 → 隐含乘子 0.85/0.70 = **1.21×**；WS3 实测档位 1.28/1.56 的机制已验证（sizing 层线性）。WS2 口径互检 (0.36,f=1)→1.56× 与冻结定义一致。
2. **1.56 否决的独立性**：WS3（A 单 sleeve 单路径，-19.3%）与 WS2（组合 MC p95，wB≥0.45 全灭）从两个独立方向得出同一结论——全回收不进预注册。
3. **WS1 门槛按 70/30 重算**（WS1 原按 64/36）：
   - 数学门槛：A 侧 1,403×0.64/0.70≈**1,283**，B 侧 915×0.36/0.30≈**1,098** → max ≈1,300（原 1,500 结论带余量仍成立）；
   - 严肃档：A 粒度 3,524×0.64/0.70≈3,222，B 补仓 ~2,900×0.36/0.30≈**3,480**（约束主从 A 换手到 B）→ **≈3,500 不变**；极价稳健 5,000 档不变。
4. **B 的 MOT 3 vs 4**：WS4 读码确认 TOP_N=3 槽位扫描使第 4 槽永无信号 → 部署 MOT 3，G0 做 diff 核验。（WS3 披露"实际 MOT=3"，与 config MOT=4 的表观差异在 G0 一并核对。）

## 3. 最终预注册包（待用户批准后冻结）

| 项 | 值 | 依据 |
|---|---|---|
| 宇宙 | BTC/ETH/SOL（Binance USDT-M 永续） | 市值预选、无幸存者偏差、6/6 年为正 |
| 容器 A | **OPT9_Recycle @ RECYCLE_MULT=1.21**，钱包 70%，3 币 | WS2 推荐 + WS3 已验证机制（1.21 为 MC 验证配置的精确隐含值；若坚持只用已实测档位则退 1.28，略激进于 MC 配置） |
| 容器 B | OPT2_MomRegime15mLb21，钱包 30%，MOT 3 | WS4 核验 MOT 等价性 |
| 信号 | BTC 已收盘日线 < SMA100（与 B 逐字同口径，shift=2 因果对齐） | WS3：与 B 公式 0 不匹配，lookahead no-bias |
| 资金 | dry-run 10k 语义（7000/3000）；**实盘 ≥5,000** | WS1+§2.3 重算 |
| 红线 | 30d 滚动 -20% 停机保留（MC p95 -18.4%，余量 1.6pp）；-25% 从峰 REVIEW 保留（**预期会触发**，非停机） | WS2 MC |
| 迟滞 | H=0（与 B 同步） | WS3 抖动分析：孤立段放大单净盈利，迟滞反而失同步 |
| 流程 | WS4 G0-G6 gate；dry-run ≥1 个完整 BTC 破线周期 | WS4 |

## 4. 全局技术警报（WS3 发现，超本任务范围）

**freqtrade 2026.8 回测态 `get_analyzed_dataframe` 只回传最近 1000 根**——任何在回测里用它算 >42 天（1h 口径）回看指标的策略都会静默拿到截断数据且无报错。与 OPT8 42 天止损 bug 同根。后果：
1. OPT9_Recycle 已改用 `get_pair_dataframe` + 严格因果切片修复；
2. **全仓库应排查同类用法**（建议列入下一次维护任务）；
3. live 部署 A 需 `startup_candle_count ≥ 2400`（SMA100 日线口径，WS3 已写入 WS4 输入）。

## 5. 遗留开放项（不阻塞预注册，G0/观察期处理）

1. 1.21 乘子为 MC 配置隐含值、机制已在 1.28/1.56 上验证——如需完全实测可补跑 1.21 单档（约 3 分钟）；
2. WS3 的 1.56 唯一逐笔分歧（2026-08-19 wallet 交互拒单）机制已知、属预期，G0 核验清单收录；
3. 实盘约束为 2026-11-03 价格快照，正式实盘前按当日价复核 WS1 §3；
4. 季度预算再平衡 ±10pp 带宽（WS4 runbook）在 dry-run 期间演练一次。

## 6. Hyperopt 终裁决（2026-11-04 补，A/B 双侧）

**结论：A、B 两侧均无可在 24-26 披露窗显著超越冻结基线的参数组合。参数面正式关死（继 INFER rank IC -0.156 后的第二、三次独立确认），预注册包（§3）不变。**

| 侧 | 赢家形态 | 24-26 判定 | 实质 |
|---|---|---|---|
| A-Sharpe | signal 2.25/stop 2.5 | 占优但 IS 三年全输、分年剧烈翻转 | regime 暴露拨盘，非可迁移 alpha |
| A-Calmar | stop 1.75 | 全窗 +2932% 但 IS 仅 +4%（噪声） | 1% 风险下名义 ×1.14 = risk_pct 变体，归风险专线 |
| B-Sharpe | PER_COIN_SMA=20 | 小幅全面占优但全窗利润 -33% | 用收益换平滑 |
| B-Calmar | tol-0.02+MPW0.60 | 持平且全窗 DD 恶化 | 闭口 Calmar 口径假象（闭口 DD 5.7% vs MTM -32.8%） |

新增认知（不改参数但改部署认知）：
1. **P2 熔断在 3 币近乎不绑定**（6 种排列同结果）——其保护对象是 12 币止损簇，3 币覆盖度不足，非最优性证据；
2. **B 的 funding 闸门在 3 币近零效应**（超阈值占比 3.5-12%，阻塞即补足）；
3. REGIME_SMA=100 是宽平台；SMA50 的 IS 优势（避开 2022 熊市 149 天 -43.2% 漂移）在 24-26 反转——regime 窗口调参=偷看周期的教科书案例；
4. B 的 MPW=0.30 有计算性风险（常开仓每 candle trim 风暴）；tol≥0 急剧恶化 DD，禁区。

方法披露：A 侧 300×2 epochs TPE@seed42；B 侧因 loky 病理+调仓风暴改为预注册 17-cell one-at-a-time 迷你网格（全时间线见 hyperopt_B.md §2）。报告：[hyperopt_A.md](hyperopt_A.md) / [hyperopt_B.md](hyperopt_B.md)。

## 7. 文件索引

- 共享上下文：[CONTEXT.md](CONTEXT.md) ｜ WS2 脚本：[ws2_analysis.py](ws2_analysis.py)（MC seed=20261103）
- 策略代码：`user_data/strategies/oss/OPT9_Recycle.py`（WS3 交付）
- 结果包：`research_ab/results/`（ws3 四个回测 zip + ws1 分布 csv）｜ 日志：`research_ab/logs/`
- 上一轮会话产物（本计划的输入）：`user_data/logs/mtm_daily_{A3,B3,S3,L3}.csv`、OPT4_DirSplit/OPT9_RiskSizing 变体
