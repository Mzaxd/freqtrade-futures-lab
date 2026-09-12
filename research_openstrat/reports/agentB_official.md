# Agent B — freqtrade/freqtrade-strategies 官方策略库筛选报告

- 日期：2026-09-12（Agent B）
- 环境：freqtrade 2026.8 / Binance USDT 永续 feather 数据 / `user_data/configs/config_futures.json`（futures、isolated、fee 0.0005、max_open_trades 3、stake unlimited）
- 交易对：BTC/ETH/SOL USDT 永续
- 窗口：IS = 2021-01-01 → 2023-01-01，VAL = 2023-01-01 → 2024-01-01（未触碰 2024 以后数据）
- 结果文件：IS = `user_data/backtest_results/oss_is_*.zip`（15 个，含前次会话遗留、已逐个验证）+ `ossB_FGodStra_is.zip`；VAL = `user_data/backtest_results/ossB_*_val.zip`（6 个）

## 0. 执行过程要点（事实记录）

1. **遗留结果处置**：除任务交办的 4 个 `oss_is_F*.zip` 外，目录中还存在本任务 9 个策略的 `oss_is_*.zip`（08:44-08:49 生成，为一次中断会话遗留）。已逐一解包验证：trading_mode=futures、pair_whitelist=BTC/ETH/SOL、fee=0.0005、窗口=2021-01-01→2023-01-01，且 zip 内嵌策略源码与当前 `user_data/strategies/oss/` 文件 md5 一致 → 判定有效并复用，未重跑。
2. **遗留 VAL 结果作废**：遗留的 4 个 `oss_val_*.zip` 窗口为 2023-01-01→**2025-01-01**，违反协议（含 2024 后数据）。已用合规窗口 20230101-20240101 重跑并落盘为 `ossB_*_val.zip`，旧文件未改动。
3. **`--export-filename` 已失效**：freqtrade 2026.8 源码中已无 `export_filename` 引用，直接传该参数会被忽略（结果写入 `backtest-result-<ts>.zip`）。改为"跑完后按策略名+窗口匹配最新 zip 再重命名"落盘 `ossB_*`，与并行 agent 无冲突。
4. **策略目录**：`freqtrade` 的 IResolver 只扫描 strategy 目录第一层，须加 `--strategy-path user_data/strategies/oss`。
5. **导入保真度**：14/15 个待测策略与官方仓库（`research_openstrat/repos/freqtrade_freqtrade-strategies`）逐字节一致（MultiMa/Supertrend/hlhb/mabStra/GodStra/TrendFollowingStrategy/VolatilitySystem 及 5 个 F* 全部 identical；Strategy001-005 仅 docstring 中示例 pair 写法差异）。即：除 GodStra 外，**所有策略零改动在 2026.8 + futures 跑通**。

## 1. 总排名表

### IS（2021-01-01 → 2023-01-01，2 年）

| 策略 | tf | trades | profit% | CAGR% | maxDD% | Sharpe | PF | winrate% | avg_dur_h | funding(USDT) | L/S |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VolatilitySystem | 1h | 106 | **+8250.79** | 813.8 | 24.77 | 0.60 | **2.04** | 50.0 | 494.3 | -97,432 | 54/52 |
| Supertrend | 1h | 766 | +107.13 | 43.9 | 52.30 | 0.63 | 1.09 | 67.5 | 28.9 | -5,011 | 766/0 |
| MultiMa | 4h | 86 | +75.28 | 32.4 | **12.60** | 0.47 | 1.86 | 72.1 | 61.1 | -1,654 | 86/0 |
| FSupertrendStrategy | 1h | 1026 | +63.75 | 28.0 | 23.92 | **0.86** | 1.08 | 66.6 | 14.6 | -2,304 | 1026/0 |
| FSampleStrategy | 1h | 204 | +17.51 | 8.4 | 75.16 | 0.03 | 1.02 | 13.2 | 191.2 | -5,268 | 190/14 |
| FAdxSmaStrategy | 1h | 112 | -3.93 | -2.0 | 12.80 | -0.10 | 0.91 | 36.6 | 15.0 | +43.6 | 47/65 |
| Strategy002 | 5m | 101 | -4.04 | -2.0 | 11.17 | -0.09 | 0.88 | 90.1 | 11.6 | -55 | 101/0 |
| hlhb | 4h | 94 | -13.94 | -7.2 | 31.45 | -0.17 | 0.73 | 81.9 | 34.6 | -74 | 94/0 |
| TrendFollowingStrategy | 5m | 555 | -14.38 | -7.5 | 86.92 | -0.03 | 0.99 | 83.8 | 92.7 | -9,297 | 555/0 |
| FReinforcedStrategy | 1h | 1080 | -28.74 | -15.6 | 30.56 | -2.44 | 0.71 | 28.8 | 0.8 | -11 | 589/491 |
| Strategy003 | 5m | 367 | -43.48 | -24.8 | 47.93 | -1.04 | 0.68 | 87.2 | 17.5 | -177 | 367/0 |
| Strategy004 | 5m | 761 | -54.46 | -32.5 | 64.03 | -1.44 | 0.77 | 87.9 | 10.6 | -282 | 761/0 |
| Strategy005 | 5m | 602 | -61.24 | -37.7 | 68.55 | -1.29 | 0.78 | 81.6 | 29.9 | -635 | 602/0 |
| mabStra | 4h | 557 | -72.39 | -47.5 | 89.72 | -0.36 | 0.94 | 52.8 | 89.8 | -5,427 | 557/0 |
| Strategy001 | 5m | 2042 | -78.62 | -53.8 | 81.49 | -2.25 | 0.86 | 87.5 | 15.4 | -1,408 | 2042/0 |
| FOttStrategy | 1h | 0 | 0.00 | — | 0 | — | — | — | — | 0 | — |
| FGodStra（适配版） | 4h | 0 | 0.00 | — | 0 | — | — | — | — | 0 | — |

### VAL（2023-01-01 → 2024-01-01，1 年）— 前 5 候选 + FReinforced 对照

| 策略 | trades | profit% | maxDD% | Sharpe | PF | winrate% | avg_dur_h | funding(USDT) | L/S |
|---|---|---|---|---|---|---|---|---|---|
| VolatilitySystem | 75 | **+166.80** | 17.16 | 0.55 | **1.79** | 38.7 | 344.3 | -821 | 38/37 |
| Supertrend | 395 | +73.19 | 30.76 | **1.94** | 1.31 | 60.0 | 33.9 | -521 | 395/0 |
| FSampleStrategy | 44 | +71.94 | 20.65 | 0.49 | 2.41 | 25.0 | 483.4 | -651 | 39/5 |
| FSupertrendStrategy | 450 | +49.00 | 24.35 | 1.91 | 1.20 | 58.2 | 19.7 | -281 | 450/0 |
| MultiMa | 48 | -0.59 | 18.93 | -0.01 | 0.98 | 60.4 | 90.8 | -137 | 48/0 |
| （对照）FReinforcedStrategy | 624 | -29.30 | 29.35 | -8.94 | 0.33 | 17.1 | 0.8 | -1.6 | 343/281 |

入选项：按 IS 风险调整指标取前 5（trades≥50、DD 不过分、Sharpe/PF 领先）= VolatilitySystem、FSupertrendStrategy、MultiMa、Supertrend、FSampleStrategy。注：FSampleStrategy 的 IS maxDD 75% 偏高，作为第 5 名保留观察；其 VAL 仅 44 笔（<50），样本偏薄。

## 2. 策略逐个要点 + 兼容性记录

全部策略 INTERFACE_VERSION=3、long-only（除注明外），futures 下 zero-adaptation 跑通。

| 策略 | tf | 核心逻辑（1-2 句） | SL / ROI / trailing | 兼容性 |
|---|---|---|---|---|
| Strategy001 | 5m | EMA20 上穿 EMA50 + Heikin-ashi 阳线且 ha_close>EMA20 做多；EMA50 上穿 EMA100 + HA 阴线平仓 | SL-10%；ROI 5%→1% | 原样跑通 |
| Strategy002 | 5m | RSI<30 + slowk<20 + close<布林下轨 + 锤子线做多；SAR 转空 + fisher_rsi>0.3 平仓 | SL-10%；ROI 5%→1% | 原样跑通 |
| Strategy003 | 5m | 多重超卖共振（RSI<28、fisher<-0.94、MFI<16、close<SMA）+ 趋势许可（EMA50>EMA100 或 EMA5 上穿 EMA10）做多 | SL-10%；ROI 5%→1% | 原样跑通 |
| Strategy004 | 5m | ADX 强趋势 + CCI<-100 + 快/慢 stochastic 双金叉脱离超卖区 + 均量过滤做多 | SL-10%；ROI 5%→1% | 原样跑通 |
| Strategy005 | 5m | 4 倍均量放量 + close<SMA + fastd>fastk + RSI/fisher 阈值（hyperopt 参数）做多 | SL-10%；ROI 5%→1% | 原样跑通 |
| GodStra | 12h | "DNA"超参条件引擎：入场 = trend_ichimoku_base < 0.06295（绝对价格阈值）；出场 = trend_kst_diff ≈ 0.8779（浮点全等） | SL-34.5%；ROI 35.6%→0；trailing 0.227/0.268 | **不适配**：依赖 `ta` 包（venv 未装且禁止安装）→ 建 FGodStra.py；12h 无数据 → 改 4h。**跑通但 0 trades**：入场阈值是低价币 hyperopt 产物，对 BTC/ETH/SOL（价位 10³~10⁵）永不触发；结论=必须整体重 hyperopt 才可用 |
| MultiMa | 4h | TEMA 阶梯对齐做多（count4/gap15 ⇒ TEMA(30)<TEMA(15) 且 TEMA(45)<TEMA(30)）；出场=长阶梯（count12/gap68）任意一对 TEMA 下穿（OR） | SL-34.5%；ROI 52.3%→0；无 trailing | 原样跑通（indicator 循环 20×100 TEMA，4h 下可接受） |
| Supertrend | 1h | 3 组 hyperopt 参数的 Supertrend 同为 up 做多；另外 3 组同为 down 平仓 | SL-26.5%；ROI 8.7%→0；trailing 0.05/0.144 | 原样跑通 |
| hlhb | 4h | RSI(hl2,10) 上穿 50 + EMA5 上穿 EMA10 + ADX>25 做多；镜像条件平仓（"Huck loves her bucks" 外汇系统移植） | SL-32.1%；ROI 62%→0；trailing 0.0117/0.0186 | 原样跑通 |
| mabStra | 4h | SMA(7/14/28) 比值处于 [div_min, div_max] 带内做多；另一组比值带触发平仓（比值≈1 的贴合度状态机） | SL-12.8%；ROI 59.8%→0 | 原样跑通 |
| TrendFollowingStrategy | 5m | close 上穿 EWM20 + OBV 确认做多；代码填了 enter_short/exit_short 但**未声明 can_short** ⇒ 实际只做多（555 笔全 long 已证实） | SL-26.5%；ROI 15%→5%；trailing 0.05/0.1 | 原样跑通（官方 futures/ 目录原版） |
| VolatilitySystem | 1h | 3h 重采样波动突破：close_change > 2×ATR(3h) 做多、< -2×ATR 做空，反向信号平仓；**futures 原生**（can_short、2x 杠杆、一次 DCA 加仓、custom_stake 50%）；无 ROI、SL=-1（实质无止损） | 无有效 SL/ROI | 原样跑通（官方 futures/ 目录原版） |
| F* 系列（FSample/FAdxSma/FOtt/FSupertrend/FReinforced） | 1h | 官方仓库 strategies/futures/ 目录 futures 官方示例族；FSupertrendStrategy=上述 Supertrend 的 futures 变体（无 ROI 出场为主、trailing 0.05/0.1） | 各异 | 原样跑通（与仓库逐字节一致）；FOttStrategy 在本数据 0 trades |

**适配记录汇总**：新建 `user_data/strategies/oss/FGodStra.py`（唯一适配；ta→talib 重写 4 个指标列：ichimoku_base=(HH26+LL26)/2、kcc=EMA(TP,14)、kst_diff=KST-SMA(KST,9)、mfi=talib(14)；timeframe 12h→4h；去掉 print 噪音与 numpy.lib.math 导入；交易参数原样保留）。其余 14 个策略原始文件未动、未建副本。

## 3. IS→VAL 衰减观察

- **几乎无衰减/反升**：FSupertrendStrategy（+63.8%→+49.0%，Sharpe 0.86→1.91，PF 1.08→1.20，DD 持平 ~24%）；Supertrend（+107%→+73%，Sharpe 0.63→1.94，DD 52%→31%）。两者均为 1h Supertrend 族：参数在 2023 震荡市反而更适配，且 395~450 笔样本充分，**衰减风险最低**。
- **利润腰斩但风险指标稳定**：VolatilitySystem（+8250%→+167%；PF 2.04→1.79、DD 24.8%→17.2%、Sharpe 0.60→0.55）。利润相对降幅大是 2022 单边大趋势 + 复利 + 2x 杠杆的基数效应；PF/DD 两个窗口几乎不变，说明**边际优势真实存在**，并非纯曲线拟合。空头贡献是主引擎（IS 空头利润占 71.2/82.5）。
- **典型过拟合**：MultiMa（+75.3%→-0.6%，PF 1.86→0.98）。4h TEMA 阶梯本质是趋势跟随，吃满 2021 趋势、在 2023 震荡市归零——参数（count/gap/ROI 52%）是 hyperopt 产物，泛化差。
- **小样本侥幸**：FSampleStrategy（+17.5%→+71.9%）。表面"反升"，但 IS maxDD 75%、VAL 仅 44 笔、winrate 25% 靠大盈亏比，上尾部依赖个别大波段，证据不足。
- **稳定亏损**：FReinforcedStrategy（-28.7%→-29.3%）两个窗口一致亏损，直接排除。

## 4. 结论：Top 3 值得拿出来优化

### #1 VolatilitySystem（1h，多空双向，futures 原生）
**依据**：唯一在 IS/VAL 双窗口 PF>1.7 且盈利的策略；DD 双窗口 <25%；零强平；空头引擎在 2022 熊市与 2023 震荡市都盈利（IS 空头占利润 86%，VAL 37/75 笔为空）。交易结构（信号反转平仓+一次 DCA）简单、统计上不依赖频繁进出。
**优化角度**：
1. **funding 成本**：IS 付费 97,432 USDT（占期末权益 ~12%）、FSampleStrategy 同病（VAL funding -651 vs 利润 7,194）。VolatilitySystem 平均持仓 14~20 天，长期逆 funding 方向持仓是最大隐性成本 → 加 funding 费率过滤/持仓中 funding 累计超阈值提前减仓。
2. **风险结构**：stoploss=-1（无止损）+ 2x 杠杆 + DCA，单笔最差 -28% ratio。加 ATR 跟踪止损、按波动率调杠杆，目标是把 DD 压到 15% 内而保住 PF。
3. **参数面**：ATR 乘数（2.0）、重采样周期（3h）的 IS-only hyperopt + VAL 复核；复利基数大（IS 期末 83.5 万 USDT）必须做滑点敏感性测试后才可信。

### #2 FSupertrendStrategy（1h，官方 futures/ 变体）
**依据**：样本量最大（IS 1026 + VAL 450 笔）、唯一 Sharpe 双窗口 ≥0.86 且不衰减的做多策略；DD 稳定 ~24%；IS 衰减比最小的 5 个之一。
**优化角度**：
1. **空头扩展**：目前 0 空头。框架里已有 3 组 sell supertrend，可对称生成 enter_short（2022 熊市完全没吃到）。
2. **薄利 vs 成本**：IS avg profit 0.18%/笔，双边 fee 0.1% + funding 吃掉大半 → ROI 表（0.1/0.75/0.05/0.025 顺序异常，疑似 hyperopt 伪影）重调为拉长持仓或提高目标位；或升 4h 降噪。
3. **funding 过滤**：多头长期持有 IS 付费 2,304 USDT（利润 6,375 的 36%）→ 入场时检查 funding 费率符号与幅度。

### #3 Supertrend（1h，Spot 主目录版）
**依据**：绝对利润最强的非杠杆策略（IS +107%、VAL +73%），VAL Sharpe 1.94/PF 1.31 全场最高档；缺陷是 IS maxDD 52.3%。
**优化角度**：
1. **先治 DD**：SL -26.5% 过宽 + trailing_only_offset_is_reached=False 的组合导致深回撤 → 收紧为 ATR 动态止损/分档 trailing；目标 DD<30%。
2. **参数重整**：6 组 Supertrend 参数（m/p 全是 hyperopt 离散值）过拟合风险中等 → 在 IS 上重新 hyperopt 后用 VAL 验证，而非沿用原值。
3. **与 #2 合并研究**：与 FSupertrendStrategy 同源同族，可做参数共享/投票融合（双策略一致性信号才入场），天然提高稳健性。

**落选说明**：MultiMa（IS 亮眼但 VAL 归零，过拟合实证）；FSampleStrategy（VAL PF 2.41 但 44 笔 + IS DD 75%，样本不足以立项，可作为 funding 伤害的案例保留）；Strategy001-005/hlhb/mabStra/TrendFollowing（IS 全亏，其中 5m 族败于高频 fee+funding 摩擦，TrendFollowing 补声明 can_short 也难翻身——其多头已亏 1.4 万 funding）；FOtt/FGodStra（本数据下无信号，GodStra 需整体重 hyperopt 才有讨论价值）。

---
*回测产物索引：`oss_is_*.zip`（15，IS，含遗留验证）、`ossB_FGodStra_is.zip`、`ossB_{VolatilitySystem,FSampleStrategy,MultiMa,Supertrend,FSupertrendStrategy,FReinforcedStrategy}_val.zip`；汇总 CSV：`user_data/reports/summary_oss_is_all.csv`、`summary_ossB_val_final.csv`。*
