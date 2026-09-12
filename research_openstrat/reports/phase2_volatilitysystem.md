# Phase 2 — OPT2_VolatilitySystem 分报告

**结论先行：预注册的两项加法（ATR 追踪止损 + 双边 funding 门控）在 IS 上全面劣化 OPT1 基线（Sharpe 0.99→0.61，DD 11.92%→21.42%，profit +424%→+55%）。归因诊断证明劣化几乎全部来自追踪止损；funding 门控在冻结阈值 0.0013 下对 IS 入场零拦截。建议 OPT2 不予晋级。**

## 改动清单（vs OPT1_VolatilitySystem，基类文件未动）

新增文件 `user_data/strategies/oss/OPT2_VolatilitySystem.py`，在 OPT1 基础上仅加两项：

1. **ATR 追踪止损**（完全照 TrendBaselineV1 范式）：`custom_stoploss` 从"初始锚定止损"升级为"初始锚定 + 有利波动后从极值追踪"：
   - 多头 `stop = max(open − stop_atr_mult×ATR_entry, max_rate − atr_trail_mult×ATR_entry)`
   - 空头 `stop = min(open + stop_atr_mult×ATR_entry, min_rate + atr_trail_mult×ATR_entry)`
   - `stoploss_from_absolute` 输出，ATR_entry = 入场信号蜡烛的 3h 重采样 ATR（`atr_raw`）。
   - 新参数 `atr_trail_mult = DecimalParameter(1.0, 5.0, default=4.2→冻结 4.1, decimals=1, space="sell")`。
2. **双边 funding 门控**：`populate_indicators` 里 `attach_funding`（严格因果：结算序列整体 shift 一个结算事件再 as-of 合并）；`enter_long &= funding_gate_long(df, funding_max)`（高正费率禁多），`enter_short &= funding_gate_short(df, funding_max)`（深负费率禁空）。新参数 `funding_max = DecimalParameter(0.0001, 0.0020, default=0.0005→冻结 0.0013, decimals=4, space="buy")`。

**冻结不动（optimize=False，不进 hyperopt 空间）**：`signal_atr_mult=2.0`、`resample_hours=3`、`stop_atr_mult=2.0`（phase-1 冻结三元组）。其余（1% 风险仓位、无 DCA、2x 杠杆、灾难 -0.30、ROI 禁用）与 OPT1 逐字一致。因无 hyperopt 参数进入 `populate_indicators`，hyperopt 未用 `--analyze-per-epoch`。

## Hyperopt（仅 IS 20210101-20230101）

- 配置：`SharpeHyperOptLoss --spaces buy sell --epochs 150 --random-state 42 -j 2`，实际空间 = buy{funding_max 0.0001–0.0020} × sell{atr_trail_mult 1.0–5.0}（820 组合，NSGA-III 采样）。
- 运行：**150/150 epochs 全部完成**，wall ≈ 21 分钟（11:12:57–11:34），无 worker 崩溃。结果文件 `user_data/hyperopt_results/strategy_OPT2_VolatilitySystem_2026-09-12_03-12-55.fthypt`，盈利 epochs **118/150**。
- 最优 epoch 134/150：`atr_trail_mult=5.0, funding_max=0.0013` → 185 笔 / +101.79% / Sharpe 0.827 / DD 16.66% / objective −0.82668。
- **高原证据**（按 bin 中位数，全 150 epochs）：

| trail bin | n | med Sharpe | med profit% | med DD% | med trades |
|---|---|---|---|---|---|
| 1.0–2.0 | 39 | −2.75…0.03 | −34…+1 | 24–35 | 274–324 |
| 2.5–3.5 | 42 | 0.09…0.50 | +4…+36 | 14–21 | 226–252 |
| 4.0 | 16 | 0.62 | +56 | 21.0 | 208 |
| 4.5 | 28 | 0.65 | +63 | 18.6 | 192 |
| 5.0 | 25 | 0.77 | +82 | 16.2 | 186 |

  - trail 维：**单调上升至空间边缘（5.0），无内点峰**——边界效应，即"追踪越少越好"，隐含趋势外推至 trail→∞ 即回到 OPT1（无追踪）行为。
  - funding 维（trail≥4.5 子集）：0.0000 档 med Sharpe 0.421（紧门控大幅有害）→ 0.0012 档 0.769 / 0.0016 档 0.778 → 0.0020 档 0.731：**0.0012–0.0019 为平坦高原**（微峰 0.0012–0.0016，与 0.0020 差异在噪声内）。
  - Top-6 epochs 全部落在 trail 4.9–5.0 × funding 0.0012–0.0019，Sharpe 0.820–0.827 —— 角部存在真实平坦区（高原确认）。

**冻结（预注册规则）**：取盈利 epochs 参数中位数 → `atr_trail_mult=4.1`，`funding_max=0.00125`（恰在 0.0012/0.0013 之间，按 0.0001 网格取整 **0.0013**）。已回填 .py 默认值；hyperopt 侧车 json（写入的 best=5.0/0.0013）已删除，.py 为唯一权威。

## 最终 IS（冻结参数 4.1 / 0.0013）vs OPT1 基线

3 对（BTC/ETH/SOL），fee 0.0005，1h，2x，IS 20210101-20230101：

| 配置 | trades | profit% | CAGR% | maxDD% | Sharpe(闭单) | Sharpe(日钱包) | PF | winrate% | funding USDT | L/S |
|---|---|---|---|---|---|---|---|---|---|---|
| **OPT2 冻结** | 210 | **+55.16** | 24.56 | **21.42** | **0.61** | 1.15 | **1.35** | 38.6 | **−685** | 114/96 |
| OPT1 基线（冻结 signal2/r3/stop2，无追踪无门控） | 139 | +424.22 | 128.96 | 11.92 | 0.99 | 2.06 | 2.37 | 35.3 | −4,190 | 74/65 |
| OPT2 默认（4.2/0.0005，sanity） | 197 | +47.39 | — | 20.46 | 0.55 | 1.04 | 1.33 | 37.6 | — | — |
| OPT2 最优角点（5.0/0.0013，hyperopt ep134） | 185 | +101.79 | — | 16.66 | 0.83 | — | 1.60 | 70 | — | — |

OPT2 冻结出场结构：trailing_stop_loss 110 笔（均 +11.12%）、stop_loss 86 笔（均 −11.03%）、exit_signal 13 笔、force_exit 1 笔——追踪把"奔跑的赢家"提前砍掉（110 次），随后再入场吃满 2×ATR 初始止损（86 次），形成损耗性换手（139→210 笔，平均持仓 11.8 天→3.8 天）。

## 归因诊断（IS，分离两项加法的贡献）

| 诊断 | trail | funding gate | trades | profit% | maxDD% | Sharpe | PF | funding USDT |
|---|---|---|---|---|---|---|---|---|
| **gate-only**（trail=99.9 等效关闭） | 关 | 0.0013 | **139** | **+424.22** | **11.92** | **0.99** | 2.37 | **−4,190** |
| **trail-only**（gate=1.0 哨兵关闭） | 4.1 | 关 | 212 | +52.01 | 21.42 | 0.59 | 1.33 | −697 |
| OPT2 冻结（两者都开） | 4.1 | 0.0013 | 210 | +55.16 | 21.42 | 0.61 | 1.35 | −685 |

- **gate-only 与 OPT1 逐项完全一致（含 L/S 74/65、funding −4,190）**：冻结阈值 0.0013 在 IS 上对 OPT1 本会持有的入场**零拦截**（BTC/ETH/SOL 结算费率在信号时点的因果可见值未超 0.13%/8h）。附带收益：该诊断同时证明追踪代码在 trail→∞ 时精确退化为 OPT1（实现正确性交叉验证）。
- **trail-only ≈ OPT2 冻结**：劣化（profit −372pp、Sharpe −0.40、DD +9.5pp）几乎全部由追踪止损贡献；门控边际贡献仅 2 笔被拦的净亏损入场（+3.15pp）。
- funding 绝对成本 −4,190→−685 的下降源于权益复利变小与持仓变短（名义敞口缩小），并非门控节省——gate-only 诊断直接证伪"门控省 funding"。

## 半年度子窗（冻结参数，IS 内 mini-WF）

| 子窗 | trades | profit% | maxDD% | Sharpe | PF | funding USDT | zip |
|---|---|---|---|---|---|---|---|
| 2021H1 (21h1) | 40 | **+1.92** | 5.60 | 0.13 | 1.09 | −321 | opt2_VolatilitySystem_21h1_is.zip |
| 2021H2 (21h2) | 52 | **+28.66** | 7.20 | 1.14 | 1.88 | −146 | opt2_VolatilitySystem_21h2_is.zip |
| 2022H1 (22h1) | 48 | **+23.49** | 9.31 | 1.19 | 1.82 | −33 | opt2_VolatilitySystem_22h1_is.zip |
| 2022H2 (22h2) | 70 | **−2.21** | 21.41 | −0.16 | 0.95 | −110 | opt2_VolatilitySystem_22h2_is.zip |

（连乘 1.0192×1.2866×1.2349×0.9779≈1.584 vs 全窗 1.552，边界持仓差异所致，一致性成立。）

**均衡性判断：不均衡。** 利润集中在 2021H2+2022H1（趋势段，合计 +52pp）；2021H1 近乎打平；2022H2 亏损 −2.21% 且最大回撤 21.41% 集中于该窗（全窗 maxDD 21.42% 即发生于 2022Q4 熊市急跌）。对照 OPT1：其利润同样高度依赖大趋势段、其 IS maxDD 谷亦在 2022-10~12——即该信号族的 regime 依赖是结构性的；但 OPT1 依赖趋势段时仍保住 22H2 之前的深复利，OPT2 则在 22H2 用追踪+止损换手把缓冲磨掉。

## 结论

1. **追踪+门控未改善 Sharpe/DD/funding**：三项全部恶化（Sharpe 0.99→0.61；DD 11.92%→21.42%；funding 绝对值虽降 84% 但归因于敞口缩小而非门控）。
2. **机理**：本系统利润来自"让 3h 突破的大趋势奔跑至反转信号"（OPT1 平均持仓 11.8 天、赢单最长 121 天）。在 3h 重采样 ATR 尺度上加追踪（即使最宽的 5.0×ATR）会在趋势中段回撤时提前锁盈，破坏"截断亏损、让利润奔跑"的原始结构；hyperopt 空间内无任何组合（150 点覆盖 820 组合空间）恢复 OPT1 水平，且 trail 维单调指向"追踪越少越好"的边界——这是对"该系统不适合 ATR 追踪"的较强证据。
3. **门控**：双边 funding 门控在本 IS 上的可用区间（0.0012–0.0019）内近似无操作（gate-only 与 OPT1 完全一致）；紧门控（≤0.0004）明显有害（med Sharpe 0.42）。不排除在费率极端的更长样本/更多对上有价值，但对本系统 IS 无增量。
4. **建议**：OPT2 不晋级；OPT1_VolatilitySystem 维持 phase-1 冻结形态。若主会话决定仍做 VAL 单发，预期结论方向不变（结构改动在 IS 无任何补偿性收益）。

## 产物

- 策略：`user_data/strategies/oss/OPT2_VolatilitySystem.py`（冻结默认 trail=4.1 / funding=0.0013；signal 2.0 / resample 3h / stop 2.0 optimize=False）
- 结果：`user_data/backtest_results/opt2_VolatilitySystem_is.zip`（+ 4 个子窗 `opt2_VolatilitySystem_{21h1,21h2,22h1,22h2}_is.zip`，各带 .meta.json）
- 日志：`user_data/logs/opt2_volsys_{defaults_is,hyperopt_e150,hyperopt_list.txt,final_is,sub_21h1,sub_21h2,sub_22h1,sub_22h2,diag_gateonly,diag_trailonly}.log`
- hyperopt 原始：`user_data/hyperopt_results/strategy_OPT2_VolatilitySystem_2026-09-12_03-12-55.fthypt`（150 epochs 全量）
- 所有迭代/回测仅用 IS 20210101–20230101；VAL 未触碰。
