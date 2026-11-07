# research_improve — 共享上下文(2026-11-07,调度:主会话)

**总目标(户主原话)**:策略在 2023/2024/2025/2026 每年都跑赢市场等权,且 2026(最差年)绝对收益为正。
**性质**:假设生成 + 可行性探索。不是解冻、不是部署依据。最终报告必须披露多重检验风险。

## 1. 基准(已冻结,勿改)

- 主基准:12 币等权(BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI),日收盘,日历年内
- 3 币等权几乎相同(参考口径)

| 年 | 12币等权 | 3币等权 | 当前 AB70/30(3币) | 缺口 |
|---|---|---|---|---|
| 2023 | **+148.6%** | +150.8% | +95% | **-54pp** |
| 2024 | **+107.7%** | +107.9% | +64% | **-44pp** |
| 2025 | -7.4% | -7.6% | +21% | ✓ |
| 2026(至11-06) | -15.1% | -15.0% | +7% | ✓(要求绝对>0) |

核心矛盾:**2023/2024 两个大牛年大幅跑输**;25/26 已达标。组合红线:30d 滚动回撤不得 < -20%。

## 2. 已有资产(本会话产出,可直接复用)

回测 zip(`user_data/backtest_results/`,按时间):
- `backtest-result-2026-11-07_03-54-11.zip` = A 袖(ARL_2x,7000,3币)**2021-01→2026-11 全窗口**:+2273.8%,终值 166,167(含末根3笔强平+397,feather末端缺)
- `backtest-result-2026-11-07_03-56-10.zip` = B 袖(冻结 OPT2,3000,3币)同窗口:+3005.9%,终值 93,176
- `2026-11-07_02-59-05` / `03-00-10` = A/B 袖 2024-01 起;`02-52-27` / `02-52-52` = 2024-12-10 起
- 逐年(3币):A: 21+171/22+115/23+123/24+38/25+26/26+6;B: 21+614/22+2/23+44/24+140/25+15/26+8;AB70/30: 21+304/22+55/23+95/24+64/25+21/26+7

## 3. 策略机制速查(重要,别重新发现)

- **A = `ARL_2x`**(类在 `user_data/strategies/oss/AB_LevGrid.py`)= `OPT9_Recycle` RECYCLE_MULT=1.21 + lev2。1h,多空,ATR突破+追踪止损。
  - **notional = equity × risk_pct / stop_pct,公式里没有杠杆项 → 杠杆 PnL 中性,真正的敞口拨盘是 `risk_pct`(默认 0.01)**。babfdef 研究:5x 杠杆中性,risk 2% ≈ 收益回撤等比放大。
  - BTC 参考数据(回收信号)来自 1h feather;OPT9 已含单边簇熔断。
- **B = `OPT2_MomRegime15mLb21`(冻结)**:15m,纯多,TOP_N=3(notional 目标=equity/TOP_N),mpw 0.45,tol -0.03,abs 资金费率门。regime 门:BTC日线 > SMA100×1.03;币自身 SMA50 趋势门;14d 动量排名。
  - **B 的 leverage() 回调是真敞口拨盘**:杠杆地图结论 B2x 甜点(21-26 +29481%/DD26.9%/0强平),B5x 被自身 kill-line 否决。
  - B 的日线 panel 从白名单币的 1d feather 读取(`_daily_closes`);单币跑时 BTC 不在白名单会让 regime 静默退化成永远 risk-on(参考 `user_data/strategies/oss/AB_RaySleeves.py` 的注入式子类写法)。
- 冻结纪律:**不许编辑任何已有策略文件**;研究子类 = 新文件,放 `user_data/strategies/oss/`,命名前缀:`lvg_`/`uni_`/`bull_`/`crash_`(import 兄弟模块要用同目录)。

## 4. 已证伪路线(不要再走)

1. 震荡期主动收割四线全灭(均值回归/网格入组合/G3防守/funding收割)— research_chop:震荡亏损=失败突破的止损,是趋势生意的保费
2. 参数调优:rank IC -0.156,24-26 hyperopt 三次"无参数胜冻结值"
3. ML on OHLCV:三次证伪
4. 横截面动量独立腿:空头结构性毒药
5. A 加杠杆:PnL 中性

## 5. 市场结构诊断(2026-11 本会话,12币)

| 年 | VR30 | 动量持续 | 币间相关 | 横截面离散 | BTC波动 |
|---|---|---|---|---|---|
| 2021 | 0.96 | 0.35 | 0.55 | 0.52 | 81% |
| 2022 | 0.71 | 0.11 | 0.77 | 0.13 | 65% |
| 2023 | 0.99 | 0.29 | 0.60 | 0.14 | 44% |
| 2024 | 1.01 | 0.32 | 0.61 | 0.20 | 53% |
| 2025 | 0.79 | 0.43 | 0.75 | 0.12 | 42% |
| 2026 | 1.26 | 0.34 | 0.76 | 0.09 | 45% |

结论:横截面离散死(0.52→0.09)、相关性升(0.55→0.76)、波动腰斩;**时序趋势活着**(2026 VR=1.26)。冻结宇宙只收 2021-12-31 前上市的币 → 结构性排除新波动源(RAYSOL 2024-12 上市,A 单币 23 个月 +45%/DD10% 证据)。

## 6. 运行配方

```bash
.venv/bin/freqtrade backtesting --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy-path user_data/strategies/oss \
  --strategy <类名> --timerange <范围> \
  --max-open-trades <MOT> -p <交易对...> \
  --dry-run-wallet <钱包> --cache none \
  --export trades --export-filename user_data/backtest_results/<你的标签>.zip \
  > research_improve/logs/<你的标签>.log 2>&1
```
- 数据:`user_data/data/binance/futures/<BASE>_USDT_USDT-{1h,15m,1d}-futures.feather` + `-1h-funding_rate.feather`。3 主币全时间框架已到 2026-11-07;**其余 9 币 15m 只到 2023-12-31、1h 到 2026-09、1d 已到最新**;需要可 `download-data -t 15m/1h/1d --timerange <起>-`。B 族策略还需要 1d feather(排名用)。
- **wallet 曲线提取**(组合合成标准法):
  - zip 内 `<strategy>_wallet.feather`:列 date/total_quote。**已知坑:最后一根K线强平的平仓不计入 feather 末端** → 用结果 JSON 里 `strategy.<类名>.profit_total_abs` 锚定终值
  - 1h 与 15m 曲线合成:`resample('h').last().ffill()` 后相加
- 逐年收益:`eq.resample('D').last()` → groupby(year) first/last;30d 滚动 DD:`d/d.rolling(30).max()-1` 的 min

## 7. 纪律(每个 agent 必须遵守)

1. **先写预注册再跑**:把候选变体清单、验收指标写进你的 `research_improve/<tag>/pre_reg.md`,然后才允许看 24-26 结果
2. 21-23 = IS(可以迭代);24-26 = **单发裁决**(每条预注册路线最多一次评估,不许回改再试)
3. 回测预算 ≤ 20 次;诚实报告失败(失败也是产出)
4. 禁止:git 操作、编辑冻结/已有策略文件、改 config;新增文件限定 `research_improve/<tag>/` 与 `user_data/strategies/oss/<前缀>_*.py`
5. 输出:`research_improve/<tag>/report.md`(裁决、逐年表 vs 基准、红线检查、诚实性披露)+ `results.json`([{"tag","cmd","zip","start_wallet","final_balance","yearly":{...},"maxdd","dd30"}])
