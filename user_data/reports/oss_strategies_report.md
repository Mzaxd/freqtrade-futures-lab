# 开源策略引入、回测与优化报告（OSS Strategies Report）

> 日期：2026-09-12 | 周期：用户指令"找开源策略→跑→优化" | 环境：freqtrade 2026.8、Binance USDT 永续、BTC/ETH/SOL、taker 0.05% 双边+真实资金费率、10k 起始、逐仓
> 数据纪律：开发/筛选仅用 IS 2021-22 + VAL 2023-24；2025-01→2026-09 仅对最终候选做一次性检验（披露：该区间曾被前两候选各评估一次，本家族参数未在其上调优）
> 来源与许可：freqtrade/freqtrade-strategies（GPL-3.0）、iterativv/NostalgiaForInfinity（GPL-3.0）；本地保留原始文件与补丁记录（git）

## 1. 引入清单与兼容性处理

- 官方仓 17 个（含 futures/ 目录 7 个）+ NostalgiaForInfinityX7（v17.5.40）共 18 个，存放于 `user_data/strategies/oss/`
- 补丁（最小改动，逐条 git 记录）：Strategy001-005 的 informative 交易对改为期货命名（`BTC/USDT`→`BTC/USDT:USDT`）；FReinforcedStrategy 参数补 `space=` 声明；GodStra 需 12h 数据（未下载）跳过
- 运行方式：`--strategy-path user_data/strategies/oss`

## 2. IS 2021-2022 初筛（16 个有效运行）

| 策略 | 收益 | MaxDD | Sharpe | PF | 交易 | 备注 |
|---|---|---|---|---|---|---|
| **Supertrend**（1h 做多） | +107.1% | 52.3% | 0.63 | 1.09 | 766 | 入围 |
| **MultiMa**（4h） | +75.3% | 12.6% | 0.47 | 1.86 | 86 | 入围 |
| **FSupertrendStrategy** | +63.8% | 23.9% | 0.86 | 1.08 | 1026 | 入围 |
| FSampleStrategy | +17.5% | 75.2% | 0.03 | 1.02 | 204 | funding -5268，弃 |
| VolatilitySystem | **+8250%** | 24.8% | 0.60 | 2.04 | 106 | **排除：stoploss=-1 无止损+加仓**，违反硬性风控（其收益来自无止损复利，非合规alpha） |
| Strategy001-005 | -43%~-79% | 48-81% | 负 | <0.9 | 101-2042 | 5m 削头皮死于成本，全灭 |
| mabStra/hlhb/TrendFollowing/FAdxSma | -4%~-72% | — | 负 | — | — | 弃 |
| FOttStrategy | 0 笔 | — | — | — | 0 | 无信号 |

## 3. VAL 2023-2024 复筛（4 入围者，对照我们的 RegimeRouter）

| 策略 | 收益 | MaxDD | Sharpe | PF | 交易 |
|---|---|---|---|---|---|
| **Supertrend** | **+123.4%** | 30.8% | **1.40** | 1.22 | 753 |
| FSupertrendStrategy | +53.0% | 20.5% | 0.92 | 1.10 | 862 |
| MultiMa | +16.5% | 18.9% | 0.20 | 1.40 | 75 |
| FReinforcedStrategy | -39.2% | 39.2% | -6.03 | 0.40 | 1035（淘汰） |
| RegimeRouter（自研对照） | +32.4% | 12.3% | 1.07 | 1.30 | 549 |

## 4. 优化（协议内：单假设/轮，IS+VAL 检验，可回滚）

### iter-15：Supertrend × 我们的 72h 动量逆向否决 → **失败，已回滚**
IS Sharpe 0.63→0.37、DD 反升至 56.4%；VAL 1.40→1.16。根因：Supertrend 的利润大量来自 trend_down 窗口内的强反弹，否决层恰好砍掉这些入场。教训：**regime 否决不可从 4h EMA 引擎迁移到 1h Supertrend 结构**。

### iter-16：Supertrend × 1d EMA200 慢趋势过滤（零拟合参数）→ **样本内成功**
| 窗口 | 上游 | +EMA200 | 变化 |
|---|---|---|---|
| IS 21-22 | +107.1% / DD 52.3% / Sharpe 0.63 / PF 1.09 | **+178.8% / DD 29.3% / Sharpe 1.00 / PF 1.26** | 全面改善 |
| VAL 23-24 | +123.4% / DD 30.8% / Sharpe 1.40 / PF 1.22 | +76.1% / **DD 19.2%** / Sharpe 1.08 / PF 1.22 | 收益让回撤 |

### 压力测试（2021-2024 合并，参考 +357.4%/Sharpe 0.98/DD 42.2%）
- 费率×2/×3：+193.1% / +112.4%（年化仍 30.8%/20.7%）✅
- 延迟 1 根：Sharpe 0.98→0.83（-15.3% ≤20%）✅
- funding×2：+236.9%（funding 成本 -14372 仍活）✅
- 分交易对：BTC +40.4%/ETH +16.9%/SOL +201%，全正 ✅（ETH 最弱）
- 诚实备注：合并窗 DD 42%——2022 型熊市对长多头系统仍是结构性伤害

## 5. 最终一次性样本外（2025-01→2026-09，市场 -29.6% 熊市）

| 候选 | 收益 | MaxDD | Sharpe | PF | 交易 | 判定 |
|---|---|---|---|---|---|---|
| SupertrendMa（OSS 优化版） | **-16.18%** | 30.4% | -0.42 | 0.88 | 269 | ❌ |
| RegimeRouter（自研，同期对照） | +11.65% | 14.2% | 0.61 | 1.15 | 518 | 5/7 过 |

**结论：开源最优策略经零拟合优化后，样本外在熊市失败。** 其收益本质是"牛市长 beta"——VAL 大牛市 +123% 与 OOS 熊市 -16% 是同一枚硬币的两面；EMA200 过滤减轻但无法消除。相反，自研 RegimeRouter（多空路由）在同一熊市样本外为正——路由架构的逆向保护在跨牛熊检验中显示出真实价值。

## 6. NFI X7 特别说明

IS 回测 +614%、84 笔全胜、零回撤——判定为**蜡烛级撮合假设下的伪影**（NFI 的限价网格/磨单/DCA 设计依赖实盘订单簿微结构，作者文档明确回测不代表实盘）。不入候选，保留运行记录供参考。

## 7. 汇总判定

- 开源策略生态现状（在我们 3 对永续、taker 成本、无杠杆滥用约束下）：5m 削头皮类全灭；1h 趋势类在牛市可观但熊市脆弱；无止损/加仓类（VolatilitySystem、NFI）回测数字不可作为合规候选。
- 最终对比：**RegimeRouter 仍是全部研究中唯一样本外为正的候选**（虽未达 Sharpe>1.2 验收线）；SupertrendMa 定位为"牛市进攻腿"潜在组件——未来可研究将其作为 RegimeRouter trend_up 态的子策略替换（属新研究周期，需重走全流程）。
- 复现：全部命令与结果 zip 在 `user_data/backtest_results/`（oss_*、opt*、st2_* 前缀），汇总 CSV/MD 在 `user_data/reports/summary_oss_*`、`summary_stress_stm`。

> 不构成投资建议；无盈利保证；回测局限性同前述各报告。
