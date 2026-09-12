# Phase 1 — OPT1_FSupertrendStrategy（FSupertrendStrategy 优化）

- Agent: C（阶段 1 优化团队）
- 日期: 2026-09-12
- 策略文件: `user_data/strategies/oss/OPT1_FSupertrendStrategy.py`（新建，未改动任何已存在文件）
- 最终 IS 回测: `user_data/backtest_results/opt1_FSupertrendStrategy_is.zip`
- 日志: `user_data/logs/opt1_fsup_bt_sanity.log`、`opt1_fsup_hyperopt.log`（+`_stdout`）、`opt1_fsup_bt_final.log`
- 全部迭代仅在 IS 窗口 20210101–20230101 进行（1h，BTC/ETH/SOL USDT 永续，fee 0.05%/边）。

## 1. 改动清单（相对 FSupertrendStrategy 原版）

| # | 改动 | 说明 |
|---|------|------|
| 1 | `can_short = True` | 激活原版源码中已存在但从未生效的空头端（3 组 sell supertrend 同为 down → enter_short；buy_m2 supertrend 转 up → exit_short），逻辑本身零改动 |
| 2 | 多头端 funding 门控 | `populate_indicators` 里 `opt_common.attach_funding()` 挂因果 `funding_rate` 列；多头入场加 `& opt_common.funding_gate_long(df, self.funding_max.value)`。空头端本阶段不加门（按任务书） |
| 3 | ROI 表重调 | 原表 `{"0":0.1,"30":0.75,"60":0.05,"120":0.025}`（30min→75% 的 hyperopt 伪影）替换为 hyperopt 结果（见 §3） |

**未动**：stoploss -0.265、trailing 0.05/0.10、6 组 supertrend m/p 参数（原值，且声明 `optimize=False` 冻结在 hyperopt 空间之外，使 buy 空间只含 `funding_max`）。

工程备注（不影响语义）：
- 6 组 supertrend 参数以 `IntParameter(..., optimize=False)` 冻结，`.range` 网格与原版一致，指标计算仍一次性预计算。
- freqtrade 2026.8 的 hyperopt `-j 2` 用 loky spawn worker，worker 内无法 `import opt_common`（ModuleNotFoundError → BrokenProcessPool）。解决：策略模块顶部把自身目录加入 `sys.path`，并以 `PYTHONPATH=user_data/strategies/oss` 启动 hyperopt。
- hyperopt 结束时 freqtrade 自动导出了 `OPT1_FSupertrendStrategy.json` 参数旁文件；为使 .py 内的手工回填保持权威，该自动生成文件已删除。

## 2. Hyperopt 配置与结果概况

```
freqtrade hyperopt --userdir user_data --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss --strategy OPT1_FSupertrendStrategy \
  --timerange 20210101-20230101 --timeframe 1h \
  --spaces buy roi --hyperopt-loss SharpeHyperOptLoss \
  --epochs 150 --random-state 42 -j 2
```

- buy 空间 = `funding_max ∈ [0.0001, 0.0020]`（4 位小数）；roi 空间 = freqtrade 内建 ROI 表生成器；sampler: NSGAIIISampler（2026.8 默认，seed=42）。
- 耗时：150 epochs ≈ 11 分 55 秒（10:44–10:56，含一次性指标预计算）。两次前置失败尝试：`--cache none` 不是合法 hyperopt 参数；loky import 问题（见上）。
- 结果文件：`user_data/hyperopt_results/strategy_OPT1_FSupertrendStrategy_2026-09-12_02-44-03.fthypt`（JSON-lines）。
- **150 个 epochs 中 0 个满足"单笔均利 > 0.3%"**：avg/trade 分布 max = 0.116%、median = -0.091%。按预注册规则取 Sharpe 最高者（epoch 127）并如实报告均利未达标。150 epochs 中仅 epoch 127 总利润为正。

## 3. 候选 ROI 表对比（Top-Sharpe epochs）

| epoch | Sharpe(objective=-S) | avg/trade | 总利润% | trades | maxDD% | funding_max | ROI 表 |
|---|---|---|---|---|---|---|---|
| **127** | **0.269 (-0.269)** | **0.116%** | **+23.03%** | 1709 | 34.4 | 0.0011 | `{"0":0.165,"202":0.072,"776":0.028,"1438":0}` |
| 131 | -0.075 | 0.080% | -4.80% | 1727 | 37.6 | 0.0014 | `{"0":0.395,"125":0.091,"660":0.028,"1560":0}` |
| 80 | -0.122 | 0.075% | -7.57% | 1734 | 51.9 | 0.0019 | `{"0":0.395,"125":0.091,"660":0.028,"1560":0}` |
| 48 | -0.124 | 0.064% | -8.65% | 1673 | 43.1 | 0.0011 | `{"0":0.184,"202":0.091,"776":0.028,"1438":0}` |

选择依据：无任何 epoch 均利 >0.3%，按预注册决策规则取 Sharpe 最高 = epoch 127（它同时也是唯一总利润为正、均利最高、maxDD 最低的 epoch，四个准则同指向，无需手工裁量）。**最终回填：ROI `{"0":0.165,"202":0.072,"776":0.028,"1438":0}`，funding_max = 0.0011**。funding_max 收敛在 0.0011（宽松端）：2021–22 三大币结算费率极少持续 >0.11%/8h，优化器实质上偏好"门近似关闭"，与"上界≈可自学关闭"的设计预期一致。

## 4. 最终 IS 指标 vs 基线

中间步骤参考（can_short + 门@0.0005 + 原版 ROI 的 sanity 回测）：1784 笔（873L/911S），+13.01%，maxDD 55.28%，Sharpe(closed) 0.19，avg/trade 0.11% —— ROI 重调把它改善到下表终值。

| 指标 | 基线（原版，全多） | OPT1 最终 | 评估 |
|---|---|---|---|
| Trades | 1026 | 1709（841L / 868S） | +66%，空头端成功激活 |
| 总利润 | +63.75% | **+23.03%** | 显著恶化 |
| 多/空利润 | +63.75% / 0 | +44.09% / **-21.06%** | 空头端净亏损 |
| maxDD | 23.92% | **34.37%** | 恶化（2022-07→12 回撤） |
| Sharpe (closed / daily-wallet) | 0.86 | 0.27 / 0.53 | 恶化 |
| Profit factor | 1.08 | 1.02 | 恶化 |
| **单笔均利** | 0.18% | **0.12%** | **未达 >0.3% 目标** |
| Funding（USDT） | -2304 | **-1537**（多 -1373 / 空 -164） | 改善（门控+持仓结构变化） |
| avg duration | 14.6h | 22.2h | 变长 |
| Win rate | — | 60.3%（1030W/679L） | — |

## 5. 空头端激活后的行为观察（分年 × 方向，profit_abs USDT）

| 年 | 多头 | 空头 | 解读 |
|---|---|---|---|
| 2021（牛） | +5701（484 笔，+0.391%/笔） | **-6128**（378 笔，-0.317%/笔） | 3 组 sell supertrend 在牛市震荡里反复翻空，空头被碾压 |
| 2022（熊） | -1292（357 笔，-0.073%/笔） | **+4040**（488 笔，+0.320%/笔） | **空头在 2022 熊市确有正贡献**（任务预期成立），均利 +0.32%/笔 |
| 2023（2 天） | 0 | -18（2 笔） | — |

空头净额 -2106 USDT：2021 牛市亏损(-6128) 大于 2022 熊市盈利(+4040)。结构上看：
- roi 出场（1201 笔，多 519/空 682）是利润引擎（合计 +121.6k 毛利）；
- `exit_signal` 出场合计 -102.4k（多 -52.0k/314 笔，空 -50.4k/133 笔），`trailing_stop_loss` 空头 -17.2k/50 笔——趋势反转出场吃掉几乎全部 ROI 利润；
- 即该 supertrend 空头端是"方向对（2022）、择时差（2021 震荡反复打脸 + 尾部 trailing 大亏）"的净负贡献。

## 6. 结论

1. 三项改动（can_short、多头 funding 门控、ROI 重调）在 IS 上**全面劣于基线**：利润 +63.75%→+23.03%，maxDD 23.92%→34.37%，Sharpe 0.86→0.27，PF 1.08→1.02。**单笔均利 0.12%，未达 >0.3% 目标**（150 epochs 的可达上限就是 0.116%，属搜索空间结构性上限：roi/门控无法弥补 exit_signal/trailing 的尾部亏损）。
2. 唯一改善项是 funding 成本 -2304→-1537 与 2022 年空头正贡献（+0.32%/笔）——证明"熊市空头有贡献"的假设方向正确，但 2021 年空头亏损更大，净值为负。
3. 建议：VAL 阶段将 OPT1 与基线一起送检（预期 OPT1 大概率劣于基线）；后续阶段若保留空头端，需要独立的空头 regime 过滤（例如仅在长期趋势向下时放行 enter_short），或干脆回退 can_short——这超出本阶段任务边界，未做。
4. 复现：`opt1_FSupertrendStrategy_is.zip` 内含本次回测的完整 strategy 快照、config、逐笔交易（含 funding_fees）与 wallet 曲线。
