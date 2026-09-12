# Agent C 报告：社区策略仓库调研（nateemma/strategies & Mastaaa1987/freqtrade-strategie）

日期：2026-09-12。环境：freqtrade 2026.8，Binance USDT 永续（BTC/ETH/SOL 三对），isolated，fee 0.0005，stake unlimited，max_open_trades 3，起始 10000 USDT。IS=20210101-20230101，VAL=20230101-20240101。策略文件：`user_data/strategies/oss/NC_*.py`（运行需 `--strategy-path user_data/strategies/oss`，本版 freqtrade 不递归扫描策略目录）。结果 zip：`user_data/backtest_results/ossC_*_{is,val}.zip`；汇总：`user_data/reports/summary_ossC_{is,val}.{csv,md}`。

---

## 1. 仓库画像

### nateemma/strategies（"Phil's Custom freqtrade Crypto Trading Strategies v2"）
- 大型个人研究仓库（约 25 个顶层目录）：以自研 `Framework/`（BaseStrategy/BaseNNStrategy + 特征归一化 + 训练引擎）为核心，上建 NNNC/NNMT/Anomaly/Sklearn/TSPredict 等 ML 策略族，辅以 GAN 数据增强和 Apple MLX 组件；另有 SimpleStrategies（约 70 个纯指标策略）、Basket（组合再平衡族）、Reversion、Funding、btc_corr 等研究线。
- 文档纪律极高：每个代表策略的 docstring 记录完整实验史，包括自我撤销（retraction）、lookahead 审计（三重独立验证）、流动性/幸存者偏差分析、跨 regime 稳健性网格。作者结论坦诚：多数信号类策略在美国现货上不跑赢市场；主 README 点名 Basket/MomentumRegimeBasket15mFast 是唯一长期稳定盈利的策略。
- 面向 BinanceUS 现货、long-only（作者明确说明因美国限制无法做空/上杠杆）；代码为 agent 辅助编写，2026 年仍在活跃迭代（最后 commit 2026-09-11，fix anomaly NaN weights）。
- 附带声称结果：Basket/Reversion/Funding 三族均有量化回测记录（窗口 P1 2021-05..2022-12 / P2 2023-01..2024-08 / P3 2024-09..2026-08，与我们 IS/VAL 部分重叠），且区分"自由出场/限流动性出场"两套数字，可信度较高。
- ML 族不可移植（需训练管线 + MLX + saved_data），SimpleStrategies 与 Framework 耦合且无附带结果。

### Mastaaa1987/freqtrade-strategie
- 极小的德语个人仓库（单 commit 浅历史，2026-02 更新 README）：仅一个策略体系 KamaFama 三个版本（KamaFama / _2 / _3），附 TradingView pine 版、两份大 whitelist config、以及 2024 年逐季度回测 txt（1m detail、244-262 对现货、max_open_trades 1-2）和 2025 年 1-2 月实盘日收益记录。
- 核心声称：KamaFama_2 以 fastk>84 小利了结把胜率推到 96-98%，2024Q1 回测 +573%（216 笔、99.1% 胜率），2024-09..2025-01 +1066%（323 笔）。
- 面向 Binance 现货超大盘山寨宇宙（250+ 对，5m）；非马丁/非网格，逻辑是"上升趋势深度回调抄底 + 超买小利出场"，但盈利模式典型地依赖尾部（少量 -25% 止损 vs 大量 +1% 级别小赢）。
- 文档薄、无风险讨论、无 lookahead 自查；质量明显低于官方库与 nateemma，但代码本身可读、可直接运行。

---

## 2. 候选与适配

合计 6 个（nateemma 4、Mastaaa 2）。排除项：NNNC/NNMT/Sklearn/TSPredict（需训练模型与 repo 内数据管线）、SimpleStrategies（Framework 耦合且作者自述跑不赢市场）、Basket 其余变体（与代表作同构）、Mastaaa KamaFama 原版（与 _2/_3 同源）。

| NC_ 文件 | 来源 | 类型 | TF | 核心逻辑 | 适配改动 |
|---|---|---|---|---|---|
| NC_MomRegime15mFast | nateemma Basket/MomentumRegimeBasket15m(+Fast) | 截面动量 + BTC regime 篮子（position adjustment 累积建仓） | 15m | BTC>日线SMA100 risk-on 且各币>自身日线SMA50 时持有 top-3 动量币；小时级换仓；退出滞回 EXIT_RANK_N=9；单笔上限 45% 仓位再平衡；进出场均限流动性 | 合并基类+子类为单文件；日线 feather 路径/命名改 Binance 永续（*_USDT_USDT-1d-futures.feather）；REGIME_REF→BTC/USDT:USDT；TOP_N=3 与 config 一致（**注意：3 币宇宙下截面选币退化为"门通过则全持"**） |
| NC_MomRegime15mLb21 | 同上（lb=21 变体） | 同上 | 15m | 同上，仅动量回看 14 天→21 天（仓库自证跨 regime 最稳值） | 同上 |
| NC_OversoldReversion | nateemma Reversion/OversoldReversion | 绝对超卖均值回归（时间出场） | 1h | RSI(14) 下穿 30 且价格低于 50 日 SMA 30% 以上时做多，固定 72h 时间出场；无止损（作者验证加止损摧毁边际）；限流动性进出 | MAX_POSITIONS 12→3（须等于 max_open_trades）；其余逻辑零改动 |
| NC_FundingCarry | nateemma Funding/FundingCarry | funding 极端反转（时间出场） | 1h | funding 90 期 z 分数 < -1.5（空头拥挤）且 BTC>500h SMA 时做多，16h 时间出场 | funding feather 路径/列名映射（date/funding_rate→dt/funding）；informative 对 BTC/USDT:USDT；其余零改动 |
| NC_KamaFama2 | Mastaaa KamaFama_2 | 上升趋势深度回调抄底 + fastk 止盈 | 5m | KAMA>FAMA>MAMA*0.981 的多头结构 + Williams%R<-61.3 + CTI<-0.715 + 距 24h 高点 -5%、距 24h 高点滚动 288 根高点 -12.5%；盈利后 fastk>84 小利出场；+5% 后 -0.2% 跟踪止损；硬止损 -25% | INTERFACE_VERSION 2→3；类改名；space='sell' 保留（2026.8 仍有效）；逻辑零改动 |
| NC_KamaFama3 | Mastaaa KamaFama_3 | MAMA/KAMA/FAMA 多头排列动量（hyperopt 宽松版） | 5m | MAMA>KAMA>FAMA + 宽松阈值（r_14>-80.2、mama_diff>0.01、cti>-0.56、RSI<90/99），出场同 _2 | 同上；hyperopt 参数内联为默认值 |

冒烟：全部通过（`--timerange 20220101-20220115` 或信号验证窗口如 20210510-20210610）。低信号策略在 1 月平静窗口 0 交易属预期，改用 2021-05 崩盘窗口验证了入场 machinery（OversoldReversion 5 笔 +43.9%、KamaFama2 41 笔 95.1% 胜率、MomRegime 2021-02 3 笔 +73.5%）。

---

## 3. 回测结果

### IS（20210101-20230101）

| 策略 | trades | profit% | CAGR% | maxDD% | Sharpe | PF | winrate% | funding(USDT)* | 市场** |
|---|---|---|---|---|---|---|---|---|---|
| NC_MomRegime15mFast | 41 | **+787.66** | 197.9 | 21.90 | 0.22 | 2.79 | 36.6 | -15286.6 | +195.0% |
| NC_MomRegime15mLb21 | 41 | +787.66 | 197.9 | 21.90 | 0.22 | 2.79 | 36.6 | -15286.6 | +195.0% |
| NC_OversoldReversion | 40 | +55.15 | 24.6 | 35.94 | 0.19 | 1.68 | 62.5 | +1685.8 | +189.4% |
| NC_KamaFama2 | 150 | +40.22 | 18.4 | 17.92 | 0.45 | 1.70 | 96.0 | +73.0 | +193.7% |
| NC_KamaFama3 | 2284 | -29.11 | -15.8 | 70.43 | -0.43 | 0.95 | 97.4 | -2459.4 | +193.7% |
| NC_FundingCarry | 62 | -7.08 | -3.6 | 17.35 | -0.10 | 0.80 | 45.2 | +224.4 | +189.4% |

*funding 为逐笔 funding_fees 净和，负=净支付。**freqtrade market change（各 TF 数据计算）。
单次回测时长：1h 策略 ~18s、KamaFama2 ~1.5min、KamaFama3 ~9min、MomRegime ~5.5min，均低于 15 分钟线，无跳过项。

### VAL（20230101-20240101，IS 表现居前 3 名；Lb21 与 Fast 在 3 币宇宙下结果逐字节相同故不重复跑）

| 策略 | trades | profit% | maxDD% | Sharpe | PF | winrate% | funding(USDT) | 市场 |
|---|---|---|---|---|---|---|---|---|
| NC_MomRegime15mFast | 26 | **+166.14** | 9.58 | 0.39 | 8.87‡ | 42.3 | -1111.0 | +393.7% |
| NC_OversoldReversion | 1 | +3.38 | 0.0 | n/a | n/a | 100 | -0.3 | +390.7% |
| NC_KamaFama2 | 7 | +2.07 | 0.0 | 0.41 | n/a | 100 | -0.7 | +390.7% |

‡篮子策略的 closed-trade PF/Calmar 是幻影（出场集中在期末），见仓库 README 自述；读 wallet 口径。
要点：MomRegime VAL 的 +166% 中 14639/16614 USDT 来自 2024-01 期末 force_exit（10-12 月开仓吃到拉升起涨）；OversoldReversion 与 KamaFama2 在 2023 低波动修复年信号枯竭（三巨头全年无 -30% 错位 / 无 -12.5% 回撤事件），属设计内行为而非故障。

### 关键结构细节（IS）
- MomRegime：41 笔全部 exit_signal；中位单笔 -2.25%、最差 -12.32%——收益来自仓位随组合增值的累积加仓（复利 beta + 择时门），代价是两年净付 15286 USDT funding（初始本金 1.5 倍的 15%）。
- OversoldReversion：39/40 时间出场；中位单笔 +4.13%、最差 -30.74%；因在 funding 为负时买入，**净收** 1686 USDT funding——永续上该策略比原版现货多一块结构性收入。
- KamaFama2：139 笔 fastk 止盈（中位 +1.15%）对 5 笔 -25% 硬止损（最差 -25.28%）+6 笔跟踪止损；盈亏结构 = 大量小赢被尾部大亏侵蚀（与仓库声称的"高胜率"模式一致）。SOL 占 102/150 笔。
- Lb21≡Fast（逐字节同结果）的机制解释：3 币宇宙下 rank≤TOP_N=3 恒真，动量排序仅影响候补排序（无候补），成员矩阵只由 regime/SMA50 门决定，与回看期无关。lb 参数在 3 币上不可辨识。

---

## 4. 复现 vs 仓库声称

| 策略 | 仓库声称 | 本复现 | 差异归因 |
|---|---|---|---|
| MomRegime15mFast | P1(2021-05..22) +38.8%/66 笔/DD46.4%，P2(2023-01..24-08) +197.1%/160 笔/DD51.4%（75 个山寨现货、capped exits） | IS(2021-22) +787.7%/41 笔/DD21.9%，VAL(2023) +166%/26 笔/DD9.6% | 宇宙完全不同：75 山寨截面选币 vs 3 巨头全持（吃到 2021 主流币牛市全 beta）；永续 vs 现货；方向一致（两窗口皆正、熊市门有效） |
| OversoldReversion | P1 +19.7% CAGR/Sharpe 0.72/DD42.6%，P2 +5.5% CAGR（14-15 流动性山寨现货） | IS +24.6% CAGR/DD35.9%/Sharpe 0.19，VAL 1 笔 +3.4% | 收益/DD 同量级；Sharpe 低因 3 币样本少 40 笔 vs 190 笔；2023 信号枯竭与原版 P2"13 笔"同向但更极端 |
| FundingCarry | 2024-26 现货含流动性约束 +6.6%/Sharpe 0.89（且自评"边际、不可部署"） | IS(2021-23) -7.1%/62 笔 | 时代+宇宙不同（其窗口 2024-26，我们 2021-23 巨头）；与作者"仅 2024-25 段为正"的自评相容 |
| KamaFama_2 | 2024Q1 现货 262 对 1m-detail：+573%/99.1% 胜率；2024-09..25-01 +1066% | IS +40.2%/96.0% 胜率，VAL 7 笔 +2.1% | 胜率复现（96%），收益不可比：其边际来自 250+ 山寨高频出现"24h 高点回撤 12.5%+"事件流，3 巨头上该事件流稀疏 1-2 个数量级 |
| KamaFama_3 | 无附带结果 | IS -29.1%/2284 笔 | 宽松条件在 5m 上过度交易，费耗 9700 USDT；hyperopt 参数疑似过拟合 |

---

## 5. 结论

### 值得拿出来优化的 Top 3

1. **NC_MomRegime15mFast（首选）**——唯一在 IS 跑赢买入持有（+788% vs +195%）且 VAL 保持正收益（+166%）、IS maxDD 21.9% 远低于市场峰谷的策略；2022 熊市的 BTC>SMA100+个股SMA50 双门被证明有效（41 笔全为信号出场、零强平）。优化角度：
   - **funding 成本是最大出血点**（IS -15286 USDT，≈ 总费耗的 94%）：在持仓/加仓条件中加入 funding 符号与分位门（如 funding z>+2 时暂停加仓或减仓）——这对原版现货作者是不可能做的，是永续环境下的新自由度；
   - 宇宙广度是原设计的核心杠杆（75 币截面选币），3 币下 lb/EXIT_RANK_N 全部不可辨识——数据扩到 10-15 币后才有参数优化空间；
   - VAL 利润集中于期末 force_exit，说明 2023-Q4 的建仓节奏偏慢，可测试 REBALANCE_HOURLY 的更细决策粒度或 MAX_POSITION_WEIGHT 提幅。

2. **NC_OversoldReversion**——单笔期望稳健（中位 +4.13%）、PF 1.68，且**在 perp 上结构性收取 funding**（IS +1686 USDT，占净利 34%），这是原现货版没有的收益增强。优化角度：
   - 信号稀缺（IS 40 笔、VAL 1 笔）：对三巨头测 DISLOCATION -20%~-25%（原仓库 -20% 在山寨含费亏损、-30% 才可行——必须在我们宇宙重验）；
   - 72h 固定持有改分段（如 +8% 提前了结 / 96h 延伸），原数据显示 72h 是峰值但那是山寨样本；
   - 对称做空端：原版受美国现货限制只能做多，perp 上可加"暴涨错位（>+30% above SMA50）做空"镜像仓，与动量书形成双向。

3. **NC_KamaFama2**——96% 胜率与 17.9% maxDD 复现了仓库声称的模式，且 IS +40% 为正。优化角度：
   - 尾部控制：5 笔 -25% 硬止损吃掉约 1700 USDT（≈40% 净利）。入场即深度超卖，硬止损恰在反弹前打出——改为时间止损（如 48h 未回正减半）或 ATR 自适应止损；保留 fastk 止盈不动；
   - fastk 阈值 84 与 +5% 后 -0.2% 跟踪参数 sweep（仓库从未提供 hyperopt 依据）；
   - 明确其宇宙依赖：三巨头仅高波动期可用，加波动率 regime 门（如 BTC 已实现 ATR 分位）控制 2023 型信号饥荒期的空转。

### 两仓库相对官方库/NFI 的质量判断
- **nateemma**：工程与研究纪律显著高于社区平均，Basket/Reversion/Funding 三族是可复用资产（自带 lookahead 审计与流动性建模，报告口径诚实到自我撤销）；但其价值大半在方法论而非可直接部署的策略——ML 族不可移植，策略本体全部为"跑不赢市场的诚实策略 + 一个 regime 篮子"。在本实验室同配置下其代表作 MomRegime（+788% IS/+166% VAL）显著优于官方库样例级策略，也优于同场测得的 NFI X7（同 lab IS +171%，agent A 口径）。取其门控/流动性框架，换永续宇宙重训，是最有价值的路径。
- **Mastaaa1987**：业余单策略仓库，文档与验证薄弱，声称收益高度依赖 250+ 山寨现货与 1m detail 成交假设，不可外推；但其"深度回调 + fastk 小利"内核在三巨头 perp 上仍给出 96% 胜率与正期望，作为尾部风险管理的教学样本与骨架可用。整体质量低于官方库与 NFI 一个档次：NFI 至少在跨市场大 whitelist 上有多版本迭代与社区验证，Mastaaa 的结果无法在其声明的宇宙之外复现量级。

### 过程记录（供复核）
- 适配文件 6 个：`user_data/strategies/oss/NC_{KamaFama2,KamaFama3,OversoldReversion,FundingCarry,MomRegime15mFast,MomRegime15mLb21}.py`（未改动任何已存在文件）。
- 回测日志：`user_data/logs/ossC_*_{is,val}.log`；结果：`user_data/backtest_results/ossC_*_{is,val}.zip`（本版 freqtrade 忽略 --export-filename，按实验室 run_backtest.sh 惯例事后重命名，仅重命名本人 9 个结果）。
- 汇总：`user_data/reports/summary_ossC_is.{csv,md}`、`summary_ossC_val.{csv,md}`。
