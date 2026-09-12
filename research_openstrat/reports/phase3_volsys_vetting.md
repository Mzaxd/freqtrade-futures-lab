# Phase 3 — OPT1_VolatilitySystem 晋级终审报告（Agent-F）

- 日期：2026-09-12
- 被审对象（冻结）：`user_data/strategies/oss/OPT1_VolatilitySystem.py`，参数 signal_atr_mult=2.0 / resample_hours=3 (3h) / stop_atr_mult=2.0（类 default，目录内无 `OPT1_VolatilitySystem.json` 参数覆盖文件，已核实）
- 配置：`user_data/configs/config_futures.json`（futures/isolated，BTC/ETH/SOL USDT 永续，起始 10,000 USDT，回测 fee=0.0005，max_open_trades=3）
- 检验窗口：全部命令 timerange ∈ 20210101-20230101（含子窗）。未执行任何起点 ≥ 20230101 的命令，未消耗新 VAL，未跑 2024+ 数据。
- 引用成绩（不重跑）：
  - IS 20210101-20230101：139 笔 / +424.22% / DD 11.92% / Sharpe 0.99 / PF 2.37 / funding -4,190 USDT
  - VAL 2023（已耗）：102 笔 / +121.76% / DD 15.06% / Sharpe 0.93 / PF 2.20

---

## 0. 工具适配说明：stress_test.py 为何不能直接复用，等价物如何实现

`scripts/stress_test.py` 逐条核查后确认**不能直接用于 OPT1_VolatilitySystem**，理由（均为代码事实）：

1. `PARAMS` 字典只登记了 `TrendBaselineV1b` / `TrendVolFundingV3b` / `DonchianBreakoutV2b`；`build_variants()` 第一行 `spec = PARAMS[strategy]` 对 OPT1_VolatilitySystem 直接 KeyError。
2. 其机制是向 `user_data/strategies/` 写临时策略文件 `_Stress_*.py`、经 `scripts/run_backtest.sh` 产出 `user_data/backtest_results/stress_{TAG}_*.zip`、`user_data/reports/summary_stress_{TAG}.csv/.md`、`user_data/logs/bt_stress_*.log` —— 全部在本次白名单（报告/`opt3_volsys_*` 日志与 zip）之外，违反铁律 2。
3. `Makefile` 的 `stress-%` 目标硬编码 timerange `20210101-20240101`（2024 起点），违反铁律 1，禁用。
4. 脚本头注释宣称 "fee uplift, per-pair and per-segment robustness"，但 `build_variants()` 实际只实现：参数 ±10%/±20% 扰动、joint +10%、delay1/delay2、skip10/skip20 —— **没有费率项，也没有 funding 项**。

等价物实现（全部不新建策略文件、不产生白名单外仓库文件）：

| stress_test.py 功能 | 本次等价实现 |
|---|---|
| 费率 ×2/×3 | freqtrade 原生 `backtesting --fee 0.001 / 0.0015`（见 §2） |
| 延迟 1/2 根 | freqtrade 原生 base64 策略机制 `--strategy "Class:<urlsafe_b64>"`：变体源码写入**系统 /tmp**（`tempfile.mkdtemp`，见 `strategy_resolver.py:281-295`），逐行复刻其 `DELAY_TMPL`（`enter_long/enter_short` 列 shift(n)），仅增加 `sys.path.insert` 指向 `user_data/strategies/oss` 以解析基类导入（见 §4） |
| 跳过 10%/20% 信号 | 同上机制，逐行复刻其 `SKIP_TMPL`（`np.random.default_rng(42)`，mask 随机置零入场信号），见 §4 |
| funding ×2 | freqtrade 无该 CLI 参数，stress_test.py 亦无该功能 → 定性估算（见 §3） |
| 参数扰动 ±10/20% | 终审清单未要求，未执行 |

结果落盘方式：所有回测用 `--backtest-directory /tmp/opt3_stage_*` 输出，事后仅将 `backtest-result-*.zip` 移为白名单名 `user_data/backtest_results/opt3_volsys_<检查项>_is.zip`（`.meta.json` 留在 /tmp，不进仓库）。已核查 `user_data/backtest_results/` 中我方产生的今日新文件仅 `opt3_volsys_*_is.zip`（12:12/12:20 出现的 `opt2_MomRegime*` 及 `.last_result.json` 12:20:30 的修改来自并行的其他 agent：其时间早于本 agent 首个回测完成时刻 12:27:43，且 `.last_result.json` 指向的 zip 名与 opt2 命名一致）。

---

## 1. 半年度一致性（检验 1）

设置：4 个子窗各独立回测（每窗 10,000 USDT 起步，复利不跨窗）。命令模板：

```
.venv/bin/freqtrade backtesting --userdir user_data --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss --strategy OPT1_VolatilitySystem \
  --timerange <子窗> --cache none --export trades --backtest-directory /tmp/opt3_stage_<hN>
```

| 子窗 | timerange | 笔数 | 利润 | 绝对利润 (USDT) | Max DD | funding (USDT) |
|---|---|---|---|---|---|---|
| 2021 H1 | 20210101-20210701 | 25 | **+76.17%** | 7,617 | 4.94% | -1,839 |
| 2021 H2 | 20210701-20220101 | 32 | **+76.82%** | 7,682 | 3.94% | -404 |
| 2022 H1 | 20220101-20220701 | 30 | **+63.93%** | 6,393 | 7.23% | -21 |
| 2022 H2 | 20220701-20230101 | 53 | **+7.40%** | 740 | 11.93% | -338 |

- **最差窗 = 2022 H2：+7.40%**，为正且远高于 -15% 红线 → 通过。
- 子窗笔数合计 140 vs 全窗 139：子窗边界强制平仓/开仓的正常边界效应。
- 子窗 funding 合计 -2,602 vs 全窗 -4,150：子窗各自从 10k 起步、equity 路径不同，不可直接加总对比，仅列示。
- 解读：利润主要由 2021 两窗与 2022H1 贡献；2022H2（低波动阴跌市）信号变密（53 笔）、胜率降至 34.0%、DD 升至 11.93%、利润近零——是该系统在 IS 内已知的最弱市况形态，如实记录（未触发红线）。

## 2. 费率压力（检验 3）

设置：全窗 20210101-20230101，`--fee 0.001`（= 基准 0.0005 ×2，模拟费率+滑点翻倍）与 `--fee 0.0015`（×3）。

| 场景 | fee | 笔数 | 利润 | 绝对利润 (USDT) | Max DD | funding (USDT) |
|---|---|---|---|---|---|---|
| 基准（引用） | 0.0005 | 139 | +424.22% | 42,422 | 11.92% | -4,190 |
| ×2 | 0.001 | 139 | **+408.97%** | 40,897 | 12.56% | -4,150 |
| ×3 | 0.0015 | 139 | **+394.75%** | 39,475 | 13.19% | -4,115 |

- **费率×3 后 IS 利润 +394.75% > +150% 门槛 → 通过**（×2/×3 相对基准仅 -15.25 / -29.47 个百分点）。
- 弹性低的原因：139 笔、平均持仓 ~11.8 天、换手低，手续费只按开/平名义各计一次；funding 与交易笔数不变（139 笔一致）证明费率参数未改变交易集合，仅影响成本。
- fee2x 复测与被审基准成绩的交叉一致性：139 笔相同、利润差恰为费率增量，说明被审 IS 成绩可复现。

## 3. funding 压力（检验 4，定性估算）

- freqtrade 无 funding ×2 的 CLI/配置参数（`--fee` 只作用于交易手续费）；`stress_test.py` 亦无 funding 功能（见 §0）→ 按预案走定性引用 + 计算过程。
- 精确基数（本次从 `opt3_volsys_fee2x_is.zip` 逐笔 `funding_fees` 求和复测）：**-4,150.29 USDT**（139 笔），与被审成绩引用值 -4,190 一致（差 40 USDT 来自费率对 equity 路径的微小扰动）。

计算过程（基准口径）：
1. 基准绝对利润 = 10,000 × 424.22% = **42,422 USDT**；funding = **-4,190 USDT**
2. funding 占利润 = 4,190 / 42,422 = **9.88%**
3. 假设全部 funding rate ×2（funding 与手续费相互独立，忽略复利二阶项，线性近似）：funding → -8,380 USDT，即**额外侵蚀 4,190 USDT**
4. 调整后利润 ≈ 42,422 − 4,190 = **38,232 USDT ≈ +382.3%**；侵蚀幅度 ~9.9 个百分点（funding 负担从占利润 9.88% 升至 ~19.8%）

交叉验证（本次 fee2x 复测口径）：4,150 / 40,897 = 10.15%；×2 → 利润 ≈ 36,747 USDT ≈ +367.5%。

结论：**funding ×2 仅侵蚀约 10% 的绝对利润，调整后利润（+367% ~ +382%）仍高于 +150% 门槛两倍以上**，不构成否决项。策略为多空对称的突破系统、平均持仓约 12 天，funding 敞口天然有限。

## 4. 信号延迟 / 跳过敏感性（检验 5）

设置：全窗 20210101-20230101，base64 内嵌变体（逐行复刻 stress_test.py 的 DELAY_TMPL / SKIP_TMPL，seed=42；机制见 §0）。延迟 = `enter_*` 信号列整体 shift(n) 根 1h K 线后再入场；跳过 = 随机 mask 置零 10%/20% 的信号行。

| 变体 | 笔数 | 利润 | 绝对利润 (USDT) | Max DD | funding (USDT) |
|---|---|---|---|---|---|
| 基准（引用） | 139 | +424.22% | 42,422 | 11.92% | -4,190 |
| delay 1 根 (1h) | 149 | **+227.80%** | 22,780 | 16.55% | -2,277 |
| delay 2 根 (2h) | 148 | **+268.33%** | 26,833 | 18.60% | -2,247 |
| skip 10% | 136 | **+333.27%** | 33,327 | 10.07% | -3,219 |
| skip 20% | 129 | **+338.94%** | 33,894 | 7.55% | -3,218 |

解读（如实）：
- **延迟敏感性显著**：入场延迟 1 根 1h K 线利润近乎减半（-196 个百分点）。这是突破型系统的典型特征——突破当根的价格优势贡献大。delay2 (268%) 高于 delay1 (228%) 并非"延迟越多越好"，而是延迟改变了整个交易集合与入场价（149/148 笔、不同止损与退出路径），该检验应读作"路径扰动下的稳健带"而非单调敏感性曲线。
- **漏单不敏感**：随机丢弃 10%/20% 信号后利润仍 +333%/+339%（skip20 略高于 skip10 为固定种子下的随机路径差异），不依赖任何单笔交易。
- 该项为清单第 5 项观察项，预注册判读基准未设门槛；结论：所有变体利润保持强正（最低 +227.8%），无变体转亏，但延迟 1 根的衰减幅度提示实盘执行时应尽快成交（策略本身用市价单，方向正确）。

## 5. lookahead-analysis（检验 6）

命令（先 `--help` 确认用法；注意该子命令不支持 `--cache`，首次尝试带 `--cache none` 报 `unrecognized arguments` 后去除重跑）：

```
.venv/bin/freqtrade lookahead-analysis --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss \
  --strategy OPT1_VolatilitySystem --timerange 20220101-20230101
```

结果（`user_data/logs/opt3_volsys_lookahead.log`）：

| strategy | has_bias | total_signals | biased_entry | biased_exit | biased_indicators |
|---|---|---|---|---|---|
| OPT1_VolatilitySystem | **No** | 20 | 0 | 0 | （空） |

- 结论：`no bias detected`，20 个受检信号零偏移 → **lookahead 无偏，通过**。
- 日志中 "funding_rate data ends at 2022-05/06" 的 WARNING 是 lookahead 工具对每个信号切片加载局部数据的正常表现，与全窗回测无关（全量 funding 数据覆盖 2019-2026，§1-§4 各全窗回测均正常计费）。
- 该命令自动执行多次切片回测，实测耗时 35 秒，可控。

## 6. 晋级记分卡与最终建议

预注册判读基准：费率×3 后 IS 利润仍 > +150% ；无单币依赖（任一单币亏损 > -20% 即依赖告警）；lookahead 无偏；半年度无 < -15% 窗 → 建议晋级 OOS；任一不满足则列出差距。

### 单币集中度明细（检验 2，全窗、各币独立 10k 起步）

| 单币 | 笔数 | 利润 | 绝对利润 (USDT) | Max DD | funding (USDT) |
|---|---|---|---|---|---|
| BTC/USDT:USDT | 53 | **+61.25%** | 6,125 | 4.10% | -513 |
| ETH/USDT:USDT | 45 | **+92.35%** | 9,235 | 9.91% | -896 |
| SOL/USDT:USDT | 41 | **+96.45%** | 9,645 | 5.01% | -1,323 |

三币笔数合计 139 = 全窗 139 笔（无跨币干扰）。最弱单币 BTC +61.25%，无任何单币亏损 → 无单币依赖。

### 记分卡（四项全过）

| # | 项目 | 结果 | 门槛 | 判定 |
|---|---|---|---|---|
| 1 | 半年度最差窗 | 2022H2 **+7.40%** | > -15% | **PASS** |
| 2 | 单币最差 | BTC **+61.25%**（三币全正，无 > -20% 亏损币） | 无单币依赖 | **PASS** |
| 3 | 费率×3 后 IS 利润 | **+394.75%**（39,475 USDT） | > +150% | **PASS** |
| 4 | lookahead | **has_bias = No**（20 信号 / 0 偏移） | 无偏 | **PASS** |

### 最终建议

**建议消耗 OOS 单发（20240101-20260912）**。四项预注册标准全部满足且均有较大安全边际（费率×3 余量 +244.75pp；最差半年窗距红线 +22.4pp；funding×2 估算后仍 +367~382%）。

附随风险提示（不构成否决，供 OOS 判读时参考）：
1. **执行时点敏感**：入场延迟 1 根 1h K 线利润近乎减半（+227.8%），OOS 复盘若用理想成交假设需打折扣；实盘依赖市价单即时成交。
2. **2022H2 型市况是已知弱点**：低波动阴跌期信号密度上升、胜率 34%、利润近零（+7.40%）；2024-2026 中若出现类似形态，预期收益质量下降。
3. 子窗/单币各自独立起步为口径选择（与被审 IS 成绩同口径），跨窗复利效应不可加总。

---

## 附录：产物清单

日志（14 个，`user_data/logs/`）：
`opt3_volsys_h1.log` `opt3_volsys_h2.log` `opt3_volsys_h3.log` `opt3_volsys_h4.log` `opt3_volsys_btc.log` `opt3_volsys_eth.log` `opt3_volsys_sol.log` `opt3_volsys_fee2x.log` `opt3_volsys_fee3x.log` `opt3_volsys_delay1.log` `opt3_volsys_delay2.log` `opt3_volsys_skip10.log` `opt3_volsys_skip20.log` `opt3_volsys_lookahead.log`

结果 zip（13 个，`user_data/backtest_results/`）：

| zip | 内容 |
|---|---|
| `opt3_volsys_h1_is.zip` | 20210101-20210701 |
| `opt3_volsys_h2_is.zip` | 20210701-20220101 |
| `opt3_volsys_h3_is.zip` | 20220101-20220701 |
| `opt3_volsys_h4_is.zip` | 20220701-20230101 |
| `opt3_volsys_btc_is.zip` | 全窗仅 BTC |
| `opt3_volsys_eth_is.zip` | 全窗仅 ETH |
| `opt3_volsys_sol_is.zip` | 全窗仅 SOL |
| `opt3_volsys_fee2x_is.zip` | 全窗 --fee 0.001 |
| `opt3_volsys_fee3x_is.zip` | 全窗 --fee 0.0015 |
| `opt3_volsys_delay1_is.zip` | 全窗 延迟 1 根变体 |
| `opt3_volsys_delay2_is.zip` | 全窗 延迟 2 根变体 |
| `opt3_volsys_skip10_is.zip` | 全窗 跳过 10% 信号变体 |
| `opt3_volsys_skip20_is.zip` | 全窗 跳过 20% 信号变体 |

（lookahead-analysis 无 zip 产物，结论在 `opt3_volsys_lookahead.log`。）

数据环境：3 对 1h futures OHLCV 覆盖 BTC 2019-09-08 起 / ETH 2019-11-27 起 / SOL 2020-09-14 起，均完整覆盖全部检验窗口；funding_rate 数据齐全。全部命令 `--cache none`（lookahead 子命令不支持该参数，未使用）。
