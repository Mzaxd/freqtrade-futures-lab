# Agent A 调研报告：NostalgiaForInfinity X7（NFI）

- 调研对象：`user_data/strategies/oss/NostalgiaForInfinityX7.py`（v17.5.70，79,352 行，3.5 MB）
- 官方仓库：`research_openstrat/repos/iterativv_NostalgiaForInfinity`
- 环境：freqtrade 2026.8（Python 3.11），Binance USDT 永续 feather 数据，fee 0.0005，isolated
- 回测协议：IS 20210101-20230101，VAL 20230101-20240101，5m，`--max-open-trades 6`，stake unlimited，全部 `--cache none`
- 日期：2026-09-12

## 0. TL;DR

- NFI X7 是一个**超大规模多头为主的多时间框架均值回归 + DCA 网格收割机**：82 个编号入场条件家族（51 多 + 31 空，默认启用 32 多 + 4 空），出场 100% 走 `custom_exit`（ROI/exit signal/trailing 全部禁用），DCA 最多 20+ 档（grind/rebuy/derisk 三套机制并行）。
- **在 3 个主流币（BTC/ETH/SOL）上几乎不交易**：VAL 全年只有 6 笔（全部在 SOL，含 2 笔空单），+6.05%；BTC/ETH 全年 0 笔。NFI 的 alpha 来自山寨币高波动，官方 futures 白名单是 70 个币对。
- 扩到 12 币对后交易量正常化（见结果表），**标的池宽度是 NFI 的硬依赖**。
- **与实验室规则直接冲突**：NFI 的核心利润机制就是 DCA（grind/rebuy/derisk 加仓摊低成本），实验室 README 禁止马丁格尔/加仓/网格。回测保留 DCA 原样执行，但任何"拿出来优化"的路线必须先解决这个合规问题（见 §6）。
- 结论（详见 §7）：**有条件地值得研究，但不值得以"原样调参"的方式纳入实验室**——它的大多数行为（3x 杠杆、无限档 DCA、仅山寨币有效）与实验室约束冲突；值得做的是把它的入场条件家族当作信号库做剪枝提取。

## 1. 架构摘要

### 1.1 总体结构

| 维度 | 内容 |
|---|---|
| 接口 | INTERFACE_VERSION 3，timeframe 5m，informative 15m/1h/4h/1d + BTC 4h |
| startup_candle_count | 800（Binance）；1d informative 实际加载 ~800 天 |
| 文件规模 | 79,352 行；单类 `NostalgiaForInfinityX7(IStrategy)` |
| 指标规模 | 入场逻辑引用 ~192 个唯一指标序列（np_view 统计），custom_exit 另引用 ~117 个；5m/15m/1h/4h/1d 五个时间框架 |
| hyperopt 参数 | **0 个**（无任何 DecimalParameter/IntParameter/...）；调参全部是类属性 + config 覆盖（`long_entry_signal_params` 等），本质不可 hyperopt |
| 运行模式 | config `trading_mode=futures` 时自动 `is_futures_mode=True`、`can_short=True`、固定杠杆 `leverage()=3.0`（rebuy/grind 模式也是 3x） |

### 1.2 入场条件家族（buy condition 组数）

按 `long/short_entry_condition_<N>_enable` 统计（代码中实际实现的编号条件）：

- **多头 51 个家族**（编号 1–193，稀疏）：normal(1-13)、pump(21-26)、quick(41-53)、rebuy(61-68)、high_profit(81-82)、rapid(101-110)、grind(120)、btc(121)、top_coins(141-145)、scalp(161-173)、实验性(192-193)
- **空头 31 个家族**（编号 501–671）：normal/pump/quick/rebuy/hp/rapid/grind/top_coins/scalp
- 默认启用：**多头 32 个，空头 4 个（501/502/542/562）**——空头仅 futures 模式生效
- 每个条件 = "市场状态保护门（protections）+ 多时间框架超卖/背离/形态逻辑"的组合；所有条件 OR 起来，enter_tag 记录命中的家族编号
- `protections_long_global` 等门控用多 TF RSI/CMF/CCI 的复合条件避免接飞刀

### 1.3 出场机制分工

| 机制 | 状态 | 说明 |
|---|---|---|
| exit signal (`populate_exit_trend`) | **恒 0** | 完全不用 |
| ROI (`minimal_roi`) | 未设置 | 不生效 |
| trailing | `trailing_stop=False` | 不用 |
| `custom_stoploss` | `use_custom_stoploss=False` | 不用 |
| freqtrade stoploss | -0.99 | 仅作爆仓兜底 |
| **`custom_exit`** | **全部出场** | 按 enter_tag 路由到 long/short_exit_{normal,pump,quick}，内部再分：exit_signals（1/2/3/4/6/8 号经典信号）、exit_main（RSI 阶梯止盈 o_0..o_n，利润 0.1%~10% 分档）、exit_williams_r、exit_dec（下降趋势出逃）、**exit_stoploss（内部 doom stop）**、profit-target 缓存 |
| 内部止损 | doom stop | v3.2（默认 system）：futures 常规模式 -0.35（初始成本口径）、rebuy 模式 -1.40、scalp/rapid -0.20 |
| hold 机制 | `hold_support_enabled=True` | hold-trades.json 指定 trade/pair 的最低出场利润 |

### 1.4 DCA / position_adjustment 规则（与实验室规则冲突点）

`position_adjustment_enable=True`，**未设置 `max_entry_position_adjustment`（= -1，无上限）**。三套并行机制（adjust_trade_position 按 enter_tag 路由）：

1. **Rebuy 模式**（tag 61-65）：3 档加仓，各 10% 初始仓位，间距 -12%/-14%/-16%；rebuy doom 阈值 -1.40（即浮亏可达初始成本 140% 才认输）
2. **Grind 机制**（v1/v2/legacy 多版本）：亏损时按 3~20 档小仓位加仓（如 grind_6：9 档，5%~13.7% 仓位，间距 -2.5%~-12%），每档设置独立"grind 止盈"（该档 +1.8%~10% 即减掉）；v2 版 `grinding_v2_max_grinds_and_buybacks = 20`
3. **Derisk 机制**：3 档逆势加仓（futures：-18%/-30% 档位触发，加 20%/30%/50% 初始仓位）+ 3 档 buyback（回调 -6%/-12%/-16% 各买回 10%）
4. 模式初始仓位系数：grind 模式 [0.20,0.30,0.40,0.50]、rapid 0.75、regular 1.0（`custom_stake_amount`）

### 1.5 兼容性（freqtrade 2026.8）

- 策略本身**无需修改**即可运行；但 freqtrade 的 `--strategy` 搜索默认不递归子目录，必须加 `--strategy-path user_data/strategies/oss`（或 config 里 `recursive_strategy_search: true`）。实验室模板命令缺这个参数会报 "Impossible to load Strategy"。
- 注意：freqtrade 2026.8 **弃用了 `--export-filename`**，结果会写成 `backtest-result-<ts>.zip`，需要事后按内容识别并重命名（本报告的 ossA_*.zip 即如此处理）。
- 回测速度：此 numpy 向量化重构版比传统 NFI 快一个量级；3 币对 × 2 年 IS 约 40 分钟（DCA 密集期 ~17-25 天/分钟），12 币对冒烟 15 天约 2 分钟。

## 2. 永续数据评估的语义（重要）

NFI 历史上是**现货多头策略**（X 系列主推 spot 白名单）；X7 已内置 futures 支持，检测到 `trading_mode=futures` 后：

- `can_short=True`：默认启用 4 个空头条件家族（501/502/542/562），VAL 中实际开出了空单
- `leverage()` 恒返回 **3.0**（isolated）：本次所有回测都以 3x 杠杆运行——利润与爆仓风险都被放大 3 倍
- funding 费用会计入：多头持仓跨 funding 结算付费（VAL 样本中 SOL 多单 funding 为负、空单为正）
- **NFI 现货调参的内部阈值（-0.35 doom 等）在 3x 杠杆下对应的价格波动只有 1/3**，但 NFI 对 futures 有独立参数组（`*_futures`），作者已适配过
- 数据缺口说明：LINK/DOT/LTC/UNI 的 funding_rate 下载持续被 Binance 403 限流拒绝，freqtrade 对缺失 funding 回退为 0 费率；这 4 个币的 funding 成本在 12 币对回测中被低估（但 NFI 持仓时长中位数仅 ~1-3 小时，funding 影响本身较小，3 币对 VAL 全年 funding 总额仅 -1.19 USDT）

## 3. 回测结果

命令模板（全部 `--cache none --strategy-path user_data/strategies/oss --max-open-trades 6`）。
（结果表见汇总 CSV：`user_data/reports/summary_ossA_nfi.*`）

### 3.1 主表

<!-- RESULTS_TABLE -->

### 3.2 与 buy&hold 对比（1d 数据，窗口首开→窗口末收）

| 窗口 | BTC | ETH | SOL | EW-3 等权 |
|---|---|---|---|---|
| IS 21-23 | -42.9%（maxDD -76.7%） | +62.3%（-79.4%） | +562.6%（-96.3%） | +194.0% |
| VAL 23-24 | +155.9%（-20.0%） | +90.9%（-27.3%） | +921.0%（-44.9%） | +389.3% |

### 3.3 关键观察

<!-- OBSERVATIONS -->

## 4. 3 对 vs 12 对：标的池宽度依赖

<!-- PAIR_WIDTH -->

## 5. 逐窗口解读

<!-- WINDOW_NOTES -->

## 6. DCA 与实验室规则的冲突说明

<!-- DCA_CONFLICT -->

## 7. 结论与优化角度

<!-- CONCLUSION -->

## 附录 A：运行清单

| 运行 | 窗口 | 币对 | 导出 |
|---|---|---|---|
| a | IS 2021-2023 | BTC/ETH/SOL | ossA_nfi_3p_is.zip |
| b | VAL 2023-2024 | BTC/ETH/SOL | ossA_nfi_3p_val.zip |
| c | IS 2021-2023 | 12 对 | ossA_nfi_12p_is.zip |
| d | VAL 2023-2024 | 12 对 | ossA_nfi_12p_val.zip |

- 12 对 = BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI（XXX/USDT:USDT）
- 新 9 对的 4h/1d informative 数据由本次调研补齐（`download-data --timeframes 4h 1d --timerange 20210101-20240101`）；原始后台下载只有 5m/15m/1h，缺 4h/1d 时 NFI 的空帧保护会让这些币对完全不触发信号
- buy&hold 基准脚本内联于本报告 §3.2（pandas 1d feather 计算）
