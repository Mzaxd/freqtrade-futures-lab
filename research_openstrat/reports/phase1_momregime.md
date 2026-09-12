# Phase 1 — OPT1_MomRegime15mFast（Agent-D）：12 币宇宙 + funding 门控 + lb 可辨识性

日期：2026-09-12 ｜ 窗口：**IS 20210101-20230101（全部命令仅 IS，未执行任何 ≥20230101 起点的回测）**
宇宙：12 币 `BASE/USDT:USDT`（BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI），15m，max_open_trades=3，起始 10,000 USDT，taker fee 0.05%（config_futures.json）。

## 1. 改动清单（相对 NC_MomRegime15mFast，未改动任何已存在文件）

新文件 `user_data/strategies/oss/OPT1_MomRegime15mFast.py`（类名同步），信号逻辑与原版逐行一致，仅以下三处 delta：

1. `populate_indicators` 增加 `opt_common.attach_funding(dataframe, metadata["pair"])`：附加因果 `funding_rate` 列（滞后一个结算周期的已结算费率；无数据 → NaN）。
2. `populate_entry_trend` 多头条件追加 `& opt_common.funding_gate_long(dataframe, self.funding_max)`：最近已结算 funding ≤ 阈值才允许开多（NaN 放行）。
3. `adjust_trade_position` 的**累积加仓分支**（`target = pv / self.TOP_N` 之前）加检查：最近 K 线 `funding_rate > funding_max` 则本轮不加仓（NaN 放行）。**MAX_POSITION_WEIGHT 剪枝与退出/限流动性出场逻辑一律未动。**
4. `funding_max = 0.0005`（0.05%/8h ≈ 年化 66%）为**固定工程阈值，不 hyperopt**——15m×12 币回测不支持本阶段的 hyperopt 预算，此为工程取舍非拟合值。

新文件 `user_data/strategies/oss/OPT1_MomRegime15mLb21.py`：上者子类，仅 `MOM_LOOKBACK_DAYS = 21`（14→21，源自仓库自证的全 regime 稳健回看值）。

## 2. 四跑指标表（全部 IS 20210101-20230101，12 币）

| 跑 | 策略 | 笔数 | 利润% | maxDD% | Sharpe | PF | funding(USDT) | 市场 | 胜率 | 中位持时(天) | 结果文件 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 冒烟 | OPT1_Fast @20220101-0115 | 0 | 0 | — | — | — | — | — | — | — | （不必存，exit=0） |
| 冒烟2 | OPT1_Fast @20210501-0615 | 5 | -5.55 | 15.0* | — | — | — | — | 60 | — | （验证门控路径，exit=0） |
| **跑2 基线** | NC_MomRegime15mFast 原版（无门控） | 75 | **+189.33** | 28.49 | 0.199 | 1.414 | -8,058.9 | +228.7% | 48.0 | 6.5 | `opt1_MomRegime12pBase_is.zip` |
| **跑3** | OPT1_Fast（lb=14+门控） | 73 | **+227.05** | 28.67 | 0.226 | 1.494 | -8,231.4 | +228.7% | 49.3 | 7.1 | `opt1_MomRegime15mFast_is.zip` |
| **跑4** | OPT1_Lb21（lb=21+门控） | 60 | **+542.50** | 36.03 | 0.291 | 1.837 | -11,827.9 | +228.7% | 43.3 | 8.0 | `opt1_MomRegime15mLb21_is.zip` |

\* 冒烟2 的 15.0% 为 6 周短窗内回撤，仅证明门控代码路径可执行。

参考（3 币宇宙，Agent C 口径）：41 笔 / +787.66% / maxDD 21.90% / Sharpe 0.22 / PF 2.79 / funding -15,286.6 / 市场 +195.0%。

**L-S 分布**：三跑全部纯多（`can_short=False`，0 笔空头）；出场 100% `exit_signal`，零强平/止损/期末强平。逐币笔数（跑2/跑3/跑4）：

| 币 | 跑2 | 跑3 | 跑4 |  | 币 | 跑2 | 跑3 | 跑4 |
|---|---|---|---|---|---|---|---|---|
| SOL | 11 | 11 | 10 |  | XRP | 4 | 4 | 6 |
| BNB | 11 | 11 | 7 |  | UNI | 4 | 4 | 2 |
| ETH | 7 | 7 | 5 |  | LINK | 4 | 4 | 3 |
| AVAX | 10 | 8 | 6 |  | LTC | 4 | 4 | 4 |
| DOT | 6 | 6 | 5 |  | ADA | 5 | 5 | 3 |
| DOGE | 5 | 5 | 5 |  | BTC | 4 | 4 | 4 |

**换手**（入场侧成交单数 / 入场名义额÷初始本金）：跑2 196 单、76.3x；跑3 170 单、83.7x；跑4 137 单、129.5x（lb21 更慢的动量 → 更少轮动但单笔仓更大，复利下名义额最高）。

**分年利润（USDT，按开仓年）**：跑2 2021 +26,326 / 2022 -7,393；跑3 2021 +31,062 / 2022 -8,358；跑4 2021 +82,511 / 2022 **-28,261**。收益全部来自 2021 regime；2022 三跑都小幅回吐（BTC>SMA100 门控挡住了大部分熊市，但 EXIT_RANK_N=9 滞回允许的波段内回吐仍在）。

## 3. lb 可辨识性结论

- 3 币宇宙（Agent C 已证）：lb14 与 lb21 结果**逐字节相同**——`rank ≤ TOP_N` 对全部白名单币恒真，排序不可辨识。
- 12 币宇宙（本次跑3 vs 跑4）：**强可辨识**。笔数 73→60、利润 +227.05%→+542.50%（2.4 倍）、PF 1.49→1.84、中位持时 7.1→8.0 天。机制：排序约束真实生效后，lb=21 的慢动量减少轮动、更久持有 2021 主升段的赢家，复利放大；代价是 maxDD 28.7%→36.0%、2022 回吐 -8.4k→-28.3k（滞回窗口内持有更久）。
- 结论：**宇宙扩容是 lb 参数可辨识的必要条件**；lb=21 在 12 币 IS 上明显优于 lb=14，方向与原仓库 lb×EXIT_RANK_N 稳健性网格的自证一致。

## 4. 门控对 funding 成本的影响（跑2 vs 跑3，同 lb=14）

| 指标 | 跑2 无门控 | 跑3 有门控 | 变化 |
|---|---|---|---|
| 利润% | +189.33 | +227.05 | **+37.7pp** |
| funding 绝对额（USDT） | -8,058.9 | -8,231.4 | **多付 172.5（未省绝对额）** |
| funding ÷ 期末权益 | 27.9% | 25.2% | -2.7pp |
| funding ÷ 净利润 | 42.6% | 36.3% | **-6.3pp（强度降 ~15%）** |
| 入场侧成交单 | 196 | 170 | -26（-13.3%） |
| 2021 利润（USDT） | +26,326 | +31,062 | +4,736 |

机制（交易级 diff）：门控**延迟/替换**了 2021 年 2–5 月资金费飙涨期的 13 笔热动量入场（AVAX/BNB/DOGE/ADA/ETH/SOL/XRP），换成 8h–4 天后更晚的 11 笔入场；少加仓 26 单。延迟入场避开了 funding 高热顶部，2021 利润更高、复利路径更大。

诚实结论：门控**没有降低绝对 funding 支出**（复利导致权益更大、持仓名义更高，绝对额反而 +172.5），它降低的是**单位利润的 funding 强度**（42.6%→36.3%）并直接改善了利润。它的实际作用是"入场时序过滤器"而非"funding 节流器"。若目标是绝对省 funding，需要更紧的阈值或在持仓期间持续减仓——超出本阶段预注册范围，未做。

## 5. 最终候选（预注册决策规则，防 cherry-pick）

规则：跑3 vs 跑4 取 IS 利润更高者；跑3 相对跑2 利润降幅 >30% 才关门控。

- 利润：跑4（+542.50%）> 跑3（+227.05%）→ **最终候选 = OPT1_MomRegime15mLb21（lb=21 + funding 门控开启）**。
- 门控：跑3 相对跑2 利润**上升**（+37.7pp），未触发关闭条件 → **门控保留**。

风险披露（不改变决策，但 VAL 前须知）：
- 跑4 maxDD 36.03%（跑2/3 约 28.5%），2022 年回吐 -28,261 USDT（峰值权益 ~92.5k 的 31%）；
- Sharpe 0.29、利润全部集中于 2021 动量 regime，2022 为净亏损年——策略本质是"regime 门控下的动量 beta 复利"；
- 12 币基线（+189.33%）显著弱于 3 币基线（+787.66%）：截面排序把 2021 年表现弱于三巨头的山寨币选入篮子，稀释了集中 beta；lb=21+门控把 12 币版本拉回 +542.50%，但仍不及 3 币退化解。若 VAL 失败，回退 3 币口径是明确的备选。

## 6. 披露

1. **LINK/DOT/LTC/UNI 无 funding 数据**（`*_USDT_USDT-1h-funding_rate.feather` 缺失，其余 8 币有）。`opt_common` 门控按 NaN 放行（设计内）；freqtrade 回测对这 4 币不计 funding 费用 → 三跑系统性**低估**这 4 币的真实持仓成本（基线同样低估，跑间对比仍有效）。日志可见双重 warning（freqtrade dataloader + opt_common）。
2. **日线 feather 起点**：9/12 币的 1d 数据从 2021-01-01 才开始 → 自身 SMA50 需 ~50 天预热，期间 trend gate NaN→False，篮子前 ~7 周实际只有 BTC/ETH/SOL（BTC 1d 自 2019-09、ETH 2019-11、SOL 2020-09）。四跑同等受影响，内部对比有效。
3. **市场基准**：12 币等权市场变化 +228.7%（3 币口径为 +195.0%）；跑4 跑赢市场，跑2/3 未跑赢——12 币下排序约束是利润的净拖累（相对满持有），lb21 扭转。
4. **运行时长**：12 币 15m×2 年全量每跑 40–90 秒（Apple Silicon），远低于任务书 15–30 分钟预估与 40 分钟停止线；无跳过项。
5. 冒烟日志：`user_data/logs/opt1_mom_smoke.log`（0 交易，2022-01 风险关闭期，符合 Agent C 同窗口观察）、`opt1_mom_smoke2.log`（5 笔，验证入场门控与加仓门控分支无异常）。全量日志：`opt1_mom_12pBase_is.log`、`opt1_mom_fast_is.log`、`opt1_mom_lb21_is.log`。
6. 结果 zip 均经 zip 内 JSON（策略名+timerange）甄别后重命名，未触碰并行 Agent 的产物；`.meta.json` 一并同步重命名。

## 7. 交付物

- `user_data/strategies/oss/OPT1_MomRegime15mFast.py`（lb=14 + funding 门控，funding_max=0.0005 固定）
- `user_data/strategies/oss/OPT1_MomRegime15mLb21.py`（lb=21 子类）= **最终候选**
- `user_data/backtest_results/opt1_MomRegime12pBase_is.zip`（跑2 基线）
- `user_data/backtest_results/opt1_MomRegime15mFast_is.zip`（跑3）
- `user_data/backtest_results/opt1_MomRegime15mLb21_is.zip`（跑4 = 最终候选）
- 本报告 `research_openstrat/reports/phase1_momregime.md`
