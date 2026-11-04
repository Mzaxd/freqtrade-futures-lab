# WS3 — OPT9_Recycle（A sleeve 动态回收乘子）实现与验证

日期 2026-11-03 | 窗口 20210101-20260912 | 3 币 BTC/ETH/SOL | OPT7_config_12p.json（MOT=4 配置，3 币实际并发上限 3）| 初始 10000 USDT，费率 0.05%
代码交付物：`user_data/strategies/oss/OPT9_Recycle.py`（OPT9_Recycle 默认 1.28；OPT9_Recycle_M10=1.0 回归；OPT9_Recycle_M156=1.56）
本文件 + `research_ab/ws3_scripts/*.py` + `research_ab/results/ws3_*.zip|csv` + `research_ab/logs/ws3_*.log`

## 0. 结论先行

1. **实现正确，回归测试通过。** 乘子=1.0 时 OPT9_Recycle 与 OPT9 原版 **472 笔逐笔全字段一致**（回归用例 b）；乘子>1 时入场/出场/止损逐字不动，唯一改动是新开仓的 stake（wrap OPT8 的 custom_stake_amount，×MULT 后 min(stake, max_stake)）。
2. **信号与 B 的开关同口径**（同一根已收盘日线、同一 SMA100 定义、TOLERANCE=0、同一 00:00 翻转边界）：对 7020 个采样时点（12h 网格 + 全部 94 个 feather 级翻转日 ±1 天逐小时）与"B 公式全历史独立重算"比对，**0 不匹配**；freqtrade lookahead-analysis（20240101-20240601）：**no bias detected**。
3. **实测效果（3 币全窗口，MTM 日曲线口径）**：

| 指标 | a 原版 OPT9 | c 回收 1.28 | d 全回收 1.56 |
|---|---|---|---|
| 总收益 | +1807.6% | **+2420.1%** | **+3082.1%** |
| CAGR | 67.8% | **76.2%** | **83.6%** |
| Sharpe（MTM 日频） | 1.70 | 1.70 | 1.69 |
| maxDD（MTM） | -35.7% | -41.0% | **-45.5%** |
| 最差 30d 滚动 | -14.9% | -17.1% | **-19.3%（距 -20% 停机线 0.7pp）** |
| 30d 滚动 < -13% 天数 | 4 | 51 | 100 |
| freqtrade 钱包口径 maxDD / PF | 31.2% / 1.52 | 36.0% / 1.47 | 40.1% / 1.41 |

Sharpe 几乎不变、CAGR +8.4pp（1.28）/ +15.8pp（1.56）——与 CONTEXT 中组合级模拟（半回收 85.5%、全回收 90.6% CAGR）方向一致。**风险结论：1.28 可部署候选；1.56 单 A sleeve 的最差 30d 滚动 -19.3% 已贴 -20% 停机红线（红线：> -20% 停机），叠加组合层其它 sleeve 相关性后大概率越线，不建议部署。** 年度拆分：回收的增益集中在 2022（+95.0%→+123.4%/+154.4%，深熊回收）；2025-26 反而小幅拖累（2026：+5.6%→+4.9%/-0.2%，熊中震荡段放大亏损）。
4. **一个重要工程发现**：freqtrade 2026.8 回测里 `get_analyzed_dataframe` 只回传截至当前时点的**最近 1000 根**（≈42 天 1h）——日线 SMA100 物理上算不出来，任务书指定的数据源不可用（首跑 1.28 与基线逐笔全同，静默失败）。改用 `get_pair_dataframe`（freqtrade 官方防前视切口：回测返回自数据起点到当前 K 线的 raw 帧 + 我方严格 `< current_time` 再切片）。详见 §3。

## 1. 信号口径对照表（我的 vs B 的）

| 维度 | B = OPT1_MomRegime15mFast | OPT9_Recycle | 一致性 |
|---|---|---|---|
| 参考对 | REGIME_REF="BTC/USDT:USDT" | RECYCLE_REF 同 | 同 |
| 窗口 | REGIME_SMA=100（日线） | RECYCLE_SMA=100（日线） | 同 |
| 容差 | REGIME_TOLERANCE=0.0 | 无容差，`close <= SMA` 为回收 ON | 同（B 的 risk_on 是严格 `>`，故相等边界两者同为 B-off/回收-on） |
| 日线来源 | 磁盘 feather 全历史（2019-09-08 起） | BTC 1h 帧重采样 1D（UTC 自然日，`resample("1D").last()`），丢未收盘当日 | 数据源不同、数值相同：1h 重采样收盘 vs 日线 feather，2020-09-01..2026-09-12 共 2203 天 **max abs diff = 0.0** |
| 对齐 | `known=close.shift(1)`，行 D 生效 = 日内 D 日用 close(D-1) vs mean(close(D-100..D-1)) | 丢弃未收盘日后最后一根 = 日 D-1，SMA100 = mean(close(D-100..D-1)) | 同一根已收盘日线、同一个 SMA 定义 |
| 生效边界 | 日线行 D 从 00:00 起 ffill 到 15m | 当日 00:00 起当日 D-1 视为已收盘（00:00 整点即翻转） | 同（00:00 边界同为"昨收今用"） |
| 因果保护 | shift(1) + 全历史 feather（无未来） | freqtrade `_set_dataframe_max_date` 切到当前 K 线 + 我方严格 `< current_time` 切片（丢当前刚开 K 线）+ 丢未收盘日 | 双重因果，见 §6 |
| 暖机 | feather 全历史，2021-01-01 起 SMA 即有效 | 帧内数据自 2020-12-23 16:00 起，SMA100 自 **2021-04-02** 起有效；此前信号 None→回收 OFF | 91 天暖机窗内 B 逐日全为 ON（feather 核实，0 天 OFF）→ 默认 OFF 恰与 B 同步，本窗口零分歧；换起始日需重查（见披露 2） |
| 迟滞 | 无（硬闸门） | RECYCLE_HYSTERESIS_DAYS=0 默认（=B 同步）；H>0 时需 raw 连续 H+1 天才翻转 | 默认逐字同步；H 供后续实验，未网格 |

## 2. 四个回测与逐笔对比

复现命令（Git Bash，工作目录 `D:\Code\AIQuant\freqtrade-futures-lab`）：

```bash
# a 基线 / b 回归 / c 1.28 / d 1.56（各自把 zip mv 走，日志同名 .log）
for S in OPT9_VolatilitySystem OPT9_Recycle_M10 OPT9_Recycle OPT9_Recycle_M156; do
  .venv/Scripts/freqtrade.exe backtesting --userdir user_data \
    --config user_data/configs/OPT7_config_12p.json --strategy-path user_data/strategies/oss \
    --strategy $S --timerange 20210101-20260912 \
    -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT --export trades --cache none \
    > research_ab/logs/ws3_<tag>.log 2>&1
done
# MTM 日曲线
.venv/Scripts/python.exe -I research_deepen/_dispatcher/scripts/dp_mtm.py \
  research_ab/results/ws3_<zip> <TAG> 2021-01-01 2026-09-13 research_ab/results/mtm_daily_ws3_<tag>.csv
# 因果断言测试（§6）
.venv/Scripts/python.exe -I research_ab/ws3_scripts/causality_test.py
# 逐笔对比 / 信号审计
.venv/Scripts/python.exe -I research_ab/ws3_scripts/trade_compare.py
.venv/Scripts/python.exe -I research_ab/ws3_scripts/signal_audit.py
```

**b（1.0）vs a：472 笔，所有导出字段逐笔一致（differing columns: NONE）——回归通过。**

**c（1.28）vs a：**
- (pair, open_date, is_short) 匹配 **472/472**；close_date / exit_reason / close_rate **100% 相同**——sizing 未改任何信号与出场（含止损；隔离 2x 下清算距离与 stake 规模无关，无 liquidation 差异）。
- 放大判定（剥离复利漂移后）：`implied = (stake_c/eq_c)/(stake_a/eq_a)`。ON 日 245 笔 98.8% implied≈1（中位 **1.0000**）；OFF 日 211 笔 99.1% implied≈1.28（中位 **1.2800**）。被放大交易占比 **46.3%**（211/456，暖机后），vs 同期日历熊态占比 49.4%（入场日构成偏差，符合预期）。
- 截断：父类 margin_cap（0.35×eq）**0/456 触发**（1% 风险 sizing 下 stake 天然 ≤ ~12-25% eq）；max_stake 截断 **2 笔**（2023-10-16 ETH implied 1.21；2026-08-19 SOL implied 0.71——被钳到连基线规模都不到，见披露 5）。全部集中在窗口尾部高权益多仓并发时段。
- 盈亏归因：OFF 日交易 pnl +154,136→+216,853（+40.6%）；ON 日交易 +21,022→+19,552（-7%，复利路径漂移所致）。

**d（1.56）vs a：**
- 匹配 471/472，匹配部分出场全同；**唯一分歧笔**：a 的 SOL 多 2026-08-19 15:00（stake 35480.7，exit_signal，+17217.7）在 d 中**未开出**——同刻 d 的 BTC 多单放大到 stake 130802.6（=1.56×权益比 1.66×基线），吃掉钱包余量，SOL 入场被 max_stake 钳到不可行而拒单；仓位了结后 d 于 09-03 补开 SOL 多（stake 41983.4，stop_loss，-2930.1）为 a 所无。两运行最终都是 472 笔属巧合。这是预期的 wallet/MOT 边缘交互（放大 sizing 的唯一行为面），除这笔外无任何信号差异。
- ON 日 245 笔 98.8% implied≈1；OFF 日 210 笔 95.7% implied≈1.56（中位 **1.5600**）；放大占比 46.2%。max_stake 截断约 **6 笔**（implied 0.61-1.42，含 2023-09-27 SOL 0.607、2026-07/08 三笔）+ 上述 1 笔拒单。margin_cap 仍 0 触发。

## 3. 实现要点与工程发现

- **1000 根上限陷阱（重要）**：首版按任务书用 `get_analyzed_dataframe("BTC/USDT:USDT","1h")` 重采样，回测里该接口只回传 `df.iloc[max_index-1000 : max_index]`（dataprovider.py L419，`MAX_DATAFRAME_CANDLES=1000`）→ 42 天日线凑不出 SMA100 → 信号恒 False → **1.28 全窗口跑出来与基线逐笔全同且无任何报错**（正是 OPT9 文档里 OPT8 清算止损 bug 的同一根源）。修复：改 `get_pair_dataframe`（回测=自数据起点的 raw 全史、freqtrade 自带 `_set_dataframe_max_date` 防前视切口；只用 close 列无需指标）。叠加我方严格 `< current_time` 切片（丢 freqtrade floor 切口保留的当前刚开 K 线）与未收盘日丢弃。20 天/单季短窗 sanity（stake 比值 1.0→1.28×权益比，翻转日 2021-12-04 当日即放大）验证修复生效。
- **tz 教训落实（d09ba64）**：时间键统一 `pd.Timestamp(...)` → naive 则 `tz_localize("UTC")`、aware 则 `tz_convert("UTC")` → `floor("ms")` 后 searchsorted；异常不再吞掉（sizing 直通并 WARNING）。
- 只包 `custom_stake_amount`：`stake = super()(...)` → 信号 ON 时 `×RECYCLE_MULT` → `min(stake, max_stake)`；MULT=1.0 时**直接原样返回（不触发信号计算）**，回归由构造保证。在建仓位永不重算 stake：乘子翻转只影响**新开仓**（K 线入场时刻一次性定 margin），与"回收不影响持仓"语义一致。
- 迟滞实现：H>0 时 raw 条件需连续 H+1 天才翻转状态（H=1 即"2 天确认"）；H=0 直接 raw（=B 同步）。合成序列单元语义已验证。

## 4. 熊态日历与抖动统计（B 公式，feather 全历史重算）

- 窗口 2081 天：B ON 1097 天 / **OFF 984 天（47.3%，可回收日占比）**。分年 OFF 占比：2021 31.2% / 2022 **92.9%** / 2023 24.4% / 2024 24.0% / 2025 46.0% / 2026 72.9%。
- **77 次翻转、77 段**；主要长段：2021-05-13..07-30 OFF(79d)、2021-12-04..2022-03-22 OFF(109d)、2022-04-22..09-12 OFF(144d)、2022-11-08..2023-01-11 OFF(65d)、2023-08-18..10-16 OFF(60d)、2024-06-15..07-15 OFF(31d)、2025-02-22..04-22 OFF(60d)、2026-10-11..2026-04-16 OFF(188d)、2026-06-02..08-19 OFF(79d)（完整分段表见 `ws3_scripts/regime_stats.py` 输出，可直接重跑）。
- **孤立穿越**：≤3 天的 OFF 段 **21 个**（共 31 天，占熊态日 3.2%）；≤3 天的 ON 段 16 个。翻转日 |close/SMA−1| 最小 0.08%、中位 1.09%——部分翻转确实边际。
- **穿越当日 A 是否开仓**：77 个翻转日中 15 日 A 有新开仓；孤立 OFF 日（31 天）中 A 开仓 8 笔。语义确认：**乘子翻转对在建仓无影响，只改变翻转后新开仓的 stake**（b/c/d 的在建仓出场全同验证了这一点）。
- **迟滞量化**：H=1 → 放大日 976 vs 984（60 天与 raw 不同，多为边界日平移）；H=2 → 976（92 天不同）。
- **建议：维持 H=0（与 B 同步）。** 理由：(a) 本窗口孤立 OFF 段的 8 笔放大单**净盈利**（a +15.9k → c +26.6k / d +42.5k），抖动不是亏损来源；(b) 真正的 DD 伤害来自长 OFF 段内的 2026H1 型震荡（maxDD 谷均为 2026-08-12），迟滞无解；(c) B 的闸门设计上无迟滞（OPT1 注释明示"hard gates"），单边给 A 加迟滞会产生 B-on/A-仍放大的过度配置窗口，加剧钱包钳制；(d) 若真要加确认，应 A、B 同改（改 B 超出 WS3 授权范围）。H 参数保留在代码里供后续预注册实验，不隐式网格。

## 5. 风险/收益与 30d 滚动（dp_mtm 日曲线，2081 天）

- 上表 §0；maxDD 谷三者同为 2026-08-12（同一事件被放大），DD 起点 a 2026-07-12 / c 2026-06-20 / d 2026-05-24——乘子越大，回撤段开始越早（放大单在 5-6 月已开始积累回撤）。
- 30d 滚动最差：-14.86% → -17.11% → -19.32%；< -13% 天数 4 → 51 → 100。**-20% 停机线**：均未触发，但 1.56 余量仅 0.7pp；-25% 峰值回撤 REVIEW 哨兵：MTM maxDD 三者全部越线（A 单 sleeve 属性，组合层以 monitor_portfolio 组合口径另行评估）。
- MTM 重建误差随乘子增大：recon_err p95 981→1550→2483、max 3149→5498→9094 USDT（大 stake 逐时路径重建的粒度误差，比例上均 <3% 期末权益）。

## 6. 前视检查

1. **独立因果断言测试**（`ws3_scripts/causality_test.py`，PASS）：对 7020 个时点（12h 全窗网格 + 94 个翻转日 ±1 天逐小时；两种帧起点模拟回测帧/全史），把"截断于 t 的切片计算"与"B 公式（全历史 feather 独立实现）"逐点比对——**0 不匹配**（截断计算=全历史参照 ⟹ 无未来依赖且与 B 对齐）；日内恒常性（信号仅日界翻转）通过；暖机 91 天 None→OFF，且该窗内 B 逐日为 ON（0 天分歧）；迟滞状态机合成序列语义正确。
2. **freqtrade lookahead-analysis**（OPT9_Recycle 1.28，20240101-20240601，3 币，27s）：`has_bias=No`，20 信号，biased entry 0 / exit 0 / indicators 无（日志 `research_ab/logs/ws3_lookahead_opt9_recycle.log`）。
3. 机制层面：回测中 `get_pair_dataframe` 被 freqtrade 以 `_set_dataframe_max_date(current_time)` 截断（源码注释"prevent lookahead bias in callbacks"）；我方再严格 `< current_time`；未收盘日丢弃规则（bin 末 +1d > ts 则丢）保证只用完整 UTC 日。

## 7. 诚实披露

1. **数据源偏离任务书**：任务指定 `get_analyzed_dataframe` 重采样；实测（freqtrade 2026.8）该接口回测态只给 1000 根，SMA100 不可算，首跑静默失败（结果与基线逐笔全同，无告警）。已改 `get_pair_dataframe` 并以 §6 双重验证因果。首跑（失败版）的 zip/日志被修正版覆盖，过程记录于本节而非原始产物。
2. **暖机语义**：帧内 SMA100 自 2021-04-02 才有效；91 天暖机默认"不放大"。已核实该窗内 B 全程 ON ⟹ 本窗口默认与 B 同步零分歧；**换回测起始日（或实盘冷启）前 100 天信号不可用**，默认退化为不放大（保守方向）。实盘部署（WS4 输入）：live 的 1h 帧长度受 `startup_candle_count`+交易所拉取限制，继承的 200 根 ⟹ 信号永远 OFF（安全退化但功能失效）；需 `startup_candle_count ≥ ~2400`（100 天）或加日线 feather 回退——注意回测中上调 startup 会改变 `gate_atr_med` 暖机从而移动 2021 年初入场，须先做信号不变性验证。
3. **MOT 口径**：config `max_open_trades=4`，3 币回测实际并发上限 3（与 lab 既有 3p 系列一致）；与 12 币 MOT4 的组合部署差异由 WS2/WS4 处理。
4. **逐笔差异**：c 与 a 零差异；d 有且仅有 1 笔入场分歧（§2，SOL 2026-08-19 拒单 / 09-03 补开），机制=放大后的钱包余量耗尽，属 sizing-only 变更的预期边缘效应；其余 471 笔出场逐字相同。
5. **比值口径**：因权益复利路径分叉，`stake_c/stake_a` 恒 ≠ 1.28/1.56；判定用剥离权益漂移的 implied 乘子（ON 日中位 1.0000、OFF 日中位 1.2800/1.5600）。权益重建用已实现盈亏近似（±3% 尾部残差，同 K 线内平仓顺序所致），个别 ON 日 implied 0.95-1.03 即此噪声。max_stake 截断计数（c≈2、d≈6+1 拒单）基于该重建，为近似值。
6. **选择效应**：1.28/1.56 为 CONTEXT 预注册点（源自 64/36 静态配比的半/全回收换算），未网格其它乘子；未测试 H>0（量化见 §4，建议 H=0）。
7. **验证范围**：本文件验证的是"A 单 sleeve + 回收乘子 overlay"的 3 币独立钱包回测；B 在此仅作信号源，并未在同一钱包中真实空置资金给 A——组合级（共享钱包、B 空仓时 A 真占用其 margin）效果属 WS2/WS4。
8. **数据与口径**：数据覆盖至 2026-09-14，窗口统一 20210101-20260912；2026 为不完整年；freqtrade 钱包 DD（31.2/36.0/40.1）与 MTM DD（35.7/41.0/45.5）定义不同，两者均列；lookahead 窗口内 funding feather 止于 2024-03-05（OPT9 不用 funding，无影响）。
9. **禁止项遵守**：未 commit/push，未修改任何已跟踪文件（`git status` 仅新增 `user_data/strategies/oss/OPT9_Recycle.py` 与 `research_ab/**`）。

## 8. 交付物清单

- 代码：`user_data/strategies/oss/OPT9_Recycle.py`（OPT9_Recycle / _M10 / _M156）
- 结果：`research_ab/results/ws3_{a,b,c,d}_*.zip`（+4 个 sanity zip）、`mtm_daily_ws3_{a,c128,d156}.csv`
- 日志：`research_ab/logs/ws3_*.log`（a/b/c/d、sanity×4、lookahead）
- 脚本：`research_ab/ws3_scripts/{regime_stats,causality_test,trade_compare,signal_audit}.py`
- 本报告：`research_ab/ws3_recycle_impl.md`
