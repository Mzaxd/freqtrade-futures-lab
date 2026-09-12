# Phase 1 — OPT1_VolatilitySystem 分报告

（Agent-B 中途超时，由主会话接手收尾：hyperopt 已完成 67/150 epochs 后 worker 崩溃，参数裁定、终版 IS 回测落盘与 VAL 单发由主会话完成。）

## 改动清单（vs oss/VolatilitySystem.py，原文件未动）

1. **ATR 止损替换 SL=-1**：`stoploss=-0.30`（灾难兜底）+ `custom_stoploss` 锚定入场时重采样 ATR（`stop_atr_mult × ATR_entry`，多空对称，`stoploss_from_absolute`）。信号用的 ATR 改为无乘数的原始 `atr_raw`（原版列内嵌 ×2.0）。
2. **单笔风险 1% 权益**（对齐 README 风险模型 / TrendBaselineV1 范式）：`notional = equity×0.01 / stop_pct`（stop_pct = stop_atr_mult×ATR/close，下限 0.5%），stake = notional/2（杠杆固定 2x 不变），保证金上限 35% 权益。
3. **移除 DCA**：`position_adjustment_enable=False`。理由：1% 风险语义要求止损距离在入场时锁定，加仓会破坏风险预算；亦符合实验室"禁加仓"惯例。原版一次 DCA 的红利由风险仓位复利替代。
4. **hyperopt 空间**：buy{signal_atr_mult 1.0–4.0, resample_hours 2–6}、sell{stop_atr_mult 1.0–4.0}；SharpeHyperOptLoss、`--analyze-per-epoch`（resample_hours 在 populate_indicators 内）、seed 42、-j 2。

## Hyperopt 结果与参数裁定

- e150 运行在 67/150 epochs 时 loky worker 崩溃（结果文件 `strategy_OPT1_VolatilitySystem_2026-09-12_02-26-50.fthypt`，epoch 表存档 `user_data/logs/opt1_volsys_hyperopt_list.txt`）。
- 67 epochs 最优（epoch 27/67）：`resample=3, signal_atr_mult=1.3, stop_atr_mult=3.6` → 476 笔 / +73.4% / objective −1.32。
- **该最优显著劣于 .py 默认参数（signal 2.0 / resample 3h / stop 2.0，即原版信号参数 + 新风险结构）**：默认组合 IS 139 笔 / +424.2% / maxDD 11.92% / 脚本 Sharpe 0.99（freqtrade 日钱包口径 2.06）/ PF 2.37。NSGA-III 采样未覆盖默认组合邻域（搜索空间 4805 组合、仅 67 点）。
- **裁定**：冻结参数 = signal 2.0 / resample 3h / stop 2.0。依据：它不是本轮搜索产物而是原版信号参数（零过拟合自由度），且在已评估的全部配置中利润与风险调整指标同时最优。已删除 e10 遗留 sidecar json（避免覆盖 .py 默认值）。

## IS / VAL（3 对，fee 0.0005，VAL 单发）

| 窗口 | trades | profit% | CAGR% | maxDD% | Sharpe | PF | winrate% | funding USDT | L/S |
|---|---|---|---|---|---|---|---|---|---|
| IS 2021-22 | 139 | +424.22 | 128.96 | **11.92** | 0.99 | 2.37 | 35.3 | **-4,190** | 74/65 |
| 基线 IS | 106 | +8,250.79 | 813.8 | 24.77 | 0.60 | 2.04 | 50.0 | -97,432 | 54/52 |
| VAL 2023 | 102 | +121.76 | 121.76 | 15.06 | 0.93 | 2.20 | 34.3 | -439 | 53/49 |
| 基线 VAL | 75 | +166.80 | 166.8 | 17.16 | 0.55 | 1.79 | 38.7 | -821 | 38/37 |

关键变化：funding 成本从 IS -97,432 降至 -4,190（-96%，风险仓位缩小名义敞口的直接效果）；复利利润 +8250% → +424% 属风险归一化的预期代价；**风险指标全面改善**（DD、Sharpe、PF 双窗口均优于基线）。0 强平。

## 结论

风险结构改造（ATR 止损 + 1% 风险仓位 + 去 DCA）方向正确：边际（PF）保住的同时把 DD 从 ~25% 压到 12–15%。过门判定见 `phase1_optimization.md` 总报告（差 Sharpe 0.07 与衰减口径）。

产物：`OPT1_VolatilitySystem.py`、`opt1_VolatilitySystem_{is,val}.zip`、日志 `user_data/logs/opt1_volsys_*`。
