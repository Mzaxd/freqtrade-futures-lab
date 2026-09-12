# Phase 2 — OPT2_FSupertrendShortRegime（FSupertrend 空头端 BTC regime 门验证）

- Agent: C2（阶段 2 优化团队）
- 日期: 2026-09-12
- 策略文件: `user_data/strategies/oss/OPT2_FSupertrendShortRegime.py`（新建，未改动任何已存在文件）
- 最终 IS 回测: `user_data/backtest_results/opt2_FSupertrendShortRegime_is.zip`
- 日志: `user_data/logs/opt2_fsup_smoke.log`、`opt2_fsup_is.log`（+`_stdout`）、`opt2_fsup_is_sma.log`（+`_stdout`）
- 全部回测仅在 IS 窗口 20210101–20230101（1h，BTC/ETH/SOL USDT 永续，fee 0.05%/边，max_open_trades=3，unlimited stake）。

## 0. 假设（phase 1 遗留）

原版 FSupertrendStrategy IS：1026 笔全多 / +63.75% / maxDD 23.92% / Sharpe 0.86 / PF 1.08。
phase 1 直接开 can_short（OPT1）：空头 2022 熊市 +4040 USDT 但 2021 牛市 -6128，空头净 -2106，IS 整体劣化至 +23.03%。
**假设**：`enter_short` 仅在 BTC 1h close < EMA200（熊市 regime）时放行，可保留 2022 空头红利、剪掉 2021 空头亏损。

## 1. 改动清单（相对 FSupertrendStrategy 原版，仅 2 项）

| # | 改动 | 说明 |
|---|------|------|
| 1 | `can_short = True` | 激活原版源码中已存在的空头端（3 组 sell supertrend 同 down → enter_short；buy_m2 转 up → exit_short），出场逻辑零改动 |
| 2 | 空头 BTC regime 门 | `informative_pairs()` 声明 BTC/USDT:USDT 1h futures；`populate_indicators` 以 pandas `ewm(span=200, adjust=False)` 计算 `btc_regime_ma` 并 `merge_informative_pair` 因果合并（candle-close 对齐，无前视）；`enter_short` 追加 `btc_close_1h < btc_regime_ma_1h` |

**未动**（多头侧零改动）：buy/sell 6 组 supertrend 参数、**原版 ROI 表** `{"0":0.1,"30":0.75,"60":0.05,"120":0.025}`、stoploss -0.265、trailing 0.05/0.10、`startup_candle_count=18`。
工程注意：EMA 用 pandas ewm 而非 talib——freqtrade 2026.8 对 informative 只按 `startup_candle_count`(18) 预载前置数据，talib EMA200 前 199 根为 NaN 会把每个回测起点封死约 8 天；ewm 从第 1 根即有值（起点约 2 周内有暖机偏差，对结论无实质影响）。
验证多头零改动的直接证据：OPT2 多头笔数 = **1026，与基线逐笔一致**（644 笔 2021 + 382 笔 2022）。

## 2. 冒烟（20220101–20220115，门方向正确性）

BTC 在该窗口 322/361 小时处于 1h EMA200 之下 → 门应放行。结果：37 笔（7 多 / **30 空**），总 +12.77%，空头 +12.24%（+1224 USDT），同期市场 -11.36%。**空门方向与触发均正确**。

## 3. 全量 IS 主结果

| 指标 | 基线（原版，全多） | OPT1（phase-1 失败版） | **OPT2 EMA200 门** | OPT2 SMA200 门（变体） |
|---|---|---|---|---|
| Trades | 1026 | 1709（841L/868S） | **1902（1026L/876S）** | 1883 |
| 总利润 | +63.75% | +23.03% | **+59.93%**（+5992.9 USDT） | +32.39% |
| 多头利润 | +63.75%（+6375 USDT） | +44.09% | +50.66%（+5066 USDT） | +47.09% |
| **空头利润** | 0 | **-21.06%（-2106 USDT）** | **+9.27%（+926.9 USDT）** | -14.70%（-1470 USDT） |
| maxDD（account） | 23.92% | 34.37% | **41.44%**（underwater 54.21%） | 42.93%（underwater 58.14%） |
| Sharpe (closed) | 0.86 | 0.27 | 0.65（daily-wallet 0.68） | 0.40 |
| Profit factor | 1.08 | 1.02 | 1.04 | 1.02 |
| Funding（USDT） | -2304 | -1537 | -2218.7 | — |
| avg duration | 14.6h | 22.2h | 20.7h | 20.7h |

（maxDD 口径 = `max_drawdown_account`，与 phase-1 报告一致。）

## 4. 空头分年盈亏（profit_abs USDT，验证门控是否剪掉 2021 空头亏损）

| 年 × 方向 | OPT1（无门） | OPT2 EMA200 门 | 变化 |
|---|---|---|---|
| 2021 多 | +5701（484 笔） | +5097（644 笔） | 多头信号同基线；组合路径差异 |
| **2021 空** | **-6128（378 笔）** | **-3216（370 笔）** | 亏损减半（-47.6%），但**笔数几乎未减**（378→370） |
| 2022 多 | -1292（357 笔） | -31（382 笔） | — |
| **2022 空** | **+4040（488 笔）** | **+4138（504 笔）** | **熊市空头红利完整保留** |
| 2023(2天) 空 | -18（2 笔） | +5.2（2 笔） | — |
| **空头净额** | **-2106** | **+927** | 门把空头端从净亏翻为净赚（+3033 USDT 改善） |

门控机制数据：BTC 1h close < EMA200 的小时占比 **2021 年 46.2%**（4051/8760）、2022 年 62.9%。1h EMA200 是约 8.3 天的快趋势过滤器，**不是牛熊年 regime 指标**——2021 牛市的深度回调（1 月、3 月、5 月崩盘、夏季震荡、11–12 月转熊起点）期间 BTC 长时间位于其下，空头在这些时段照样放行并被碾压。且 supertrend 翻空信号与"BTC 跌破 1h EMA200"高度共线（同源趋势逻辑），门对空单**频率**几乎无过滤作用（370 vs 378），只通过择时略降单笔severity。

多头侧：1026 笔与基线逐笔同数，利润 +6375 → +5066（-1309 USDT）为纯组合效应（空头占槽改变 unlimited-stake 的仓位切分与复利路径），非信号差异。

空头出场病理与 OPT1 相同，门控不治本：`roi` 出场 +92.2k/706 笔，`exit_signal` -65.3k/143 笔，`trailing_stop_loss` -25.2k/24 笔——趋势反转出场几乎吃光 ROI 引擎利润。

## 5. 变体对比（IS 内，共 2 个：EMA200 主版 + SMA200）

SMA200（rolling 200，更慢、更滞后）：+32.39%，空头净 **-1470**，maxDD 42.93%，Sharpe 0.40——**全面劣于 EMA200 门**。慢均线进熊市更晚、在 2021 修复期停留更久，反向选择。两变体均远逊基线，无需第三变体。

## 6. 预注册 VAL 门槛判定

> IS 总利润 ≥ +63.75%（不低于原版基线）且 maxDD ≤ 24% → 值得 VAL

- 总利润 **+59.93% < +63.75%** → 未达标
- maxDD **41.44% ≫ 24%** → 未达标

**双双未过预注册门槛：假设在本操作化（BTC 1h EMA200 门）下证伪，不送 VAL。**

## 7. 结论

1. 门的**方向性收益成立但量级不足**：空头净额 -2106 → +927，2022 空头红利完整保留（+4138）；2021 空头亏损减半（-6128 → -3216）但未剪除。
2. 即便空头端转正，组合仍输给基线：多头端 -1309 USDT 的组合拖累 + 2021 残余空头亏损 -3216，使总利润 +59.93% < +63.75%，且 maxDD 23.92% → 41.44% 大幅恶化（回撤主因是空头端与多头共槽后的深回撤叠加）。
3. 根因（供后续阶段参考，未实施）：1h EMA200 与 supertrend 入场信号共线，只是更慢的同源过滤器；若要真正隔离 2021/2022，需要**慢周期 regime**（如 1d MA200/EMA 或更长），或重构空头出场（exit_signal/trailing 的 -90.5k 合计亏损才是空头端的主要出血点）。这超出本阶段边界。
4. 建议主会话：**不消耗 VAL 单发**；FSupertrend 系在 IS 上的最优形态仍是原版全多基线。

## 8. 复现

```
# 冒烟（门触发验证）
.venv/bin/freqtrade backtesting --userdir user_data --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss --strategy OPT2_FSupertrendShortRegime \
  --timerange 20220101-20220115 --timeframe 1h --cache none --export none \
  --logfile user_data/logs/opt2_fsup_smoke.log

# 全量 IS（导出 = opt2_FSupertrendShortRegime_is.zip 的来源）
.venv/bin/freqtrade backtesting --userdir user_data --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss --strategy OPT2_FSupertrendShortRegime \
  --timerange 20210101-20230101 --timeframe 1h --cache none --export trades \
  --logfile user_data/logs/opt2_fsup_is.log

# SMA200 变体：把策略内 regime_ma 改为 "sma" 后同命令重跑（--export none），
# 跑完已恢复为 "ema"，与导出 zip 内的策略快照一致。
```

zip 内含：完整策略快照、config、逐笔交易（含 funding_fees）、wallet 曲线与 market_change。
