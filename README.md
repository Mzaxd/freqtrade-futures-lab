# freqtrade-futures-lab

本地 Freqtrade 加密永续合约（USDT-M Perp）回测研究系统。**两个研究周期**：周期一（单策略趋势研究，结论"不推荐"，见 `reports/final_conclusion.md`）；周期二（**市场状态识别 + 策略路由架构**，本节，结论"未达验收、停止迭代"，见 `reports/STOPPED_REPORT.md`）。目标不是"稳定赚钱"，而是**过程严谨、结果可复现、风险透明**。

## 周期二：状态识别 + 路由架构（当前）

```
第一层 regime_detector.py（独立模块，因果）
  mom_z = 72h动量t统计量 → {趋势涨, 趋势跌, 震荡} + ATR分位≥0.90 → {混乱}
  驻留平滑(2根)；阈值 1.25 仅 IS 2021-22 选定
        ↓ regime CSV（逐时，因果）
第二层 regime_router.py（逆向否决制 + 状态分级仓位）
  趋势腿（EMA20/50/200 对齐）：非逆向状态可交易；同向态满风险/震荡态0.5×；逆向态退出
  meanrev 腿：仅震荡态，conf 缩放
  混乱态：禁新仓（持仓保留）
        ↓ 三个 4h 子策略（独立可运行：sub_standalone.py）
第三层 验证：路由增益(6.4✓) → WF(3胜1负) → 压力(6.2全过) → OOS 一次性(6.1: 5/7, ❌Sharpe/PF)
```

| 窗口 | 收益 | MaxDD | Sharpe | PF | 交易 | 用途 |
|---|---|---|---|---|---|---|
| IS 2021-22 | +7.77% | 15.0% | 0.29 | 1.08 | 513 | 开发（13 轮迭代） |
| VAL 2023-24 | +31.74% | 11.54% | 1.10 | 1.32 | 549 | 路由增益（✓ 超所有子策略） |
| WF 4×6m | 最差 -1.5% | ≤8.3% | — | — | ~140/窗 | 滚动检验 |
| 压力参考 21-24 | +41.98% | 15.1% | 0.73 | 1.21 | 1060 | 6.2 全过 |
| **OOS 2025-26** | **+11.65%（市场-29.6%）** | 14.19% | **0.61** | **1.15** | 518 | **5/7 过，Sharpe/PF 未达 → 停止** |

一键复现：`bash scripts/run_all.sh`（OOS 步骤显式 guarding，须手动一次执行）。
逐轮记录：`user_data/reports/iteration_log.md`（14 轮，git 逐轮提交）。

## 周期一：单策略研究（存档）

> ⚠️ 免责声明：本仓库不包含任何盈利承诺。回测存在固有局限。所有结论以证据为准，样本外失败就写失败。

## 1. 环境与版本（可复现性）

| 组件 | 版本 | 固定方式 |
|---|---|---|
| macOS | 26.5.2 arm64 | 宿主机 |
| Python | 3.11.15 | `.venv`（`uv venv --python 3.11`） |
| freqtrade | **2026.8** | `requirements.txt` 固定 |
| ccxt | 4.5.64（随 freqtrade 依赖解析） | 锁定于安装日志 |
| 交易所 | Binance USDT-M 永续（futures / isolated） | `user_data/configs/config_futures.json` |

复现安装：

```bash
uv venv --python 3.11 .venv        # 或 python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/freqtrade --version      # 应输出 freqtrade 2026.8
```

Docker 备选（本机 Docker daemon 不可用，未用于本研究，仅备用）：`docker compose up -d`（镜像 tag 同为 2026.8）。

## 2. 目录结构

```
freqtrade-futures-lab/
├── README.md                    # 本文件
├── Makefile                     # 一键命令
├── requirements.txt             # 固定版本依赖
├── docker-compose.yml           # dry-run 备用容器
├── scripts/
│   ├── download_data.sh         # 数据下载（K线/标记价/资金费率）
│   ├── build_funding_from_vision.py  # 403兜底：从 data.binance.vision 构建资金费率
│   ├── run_backtest.sh          # 单次回测（命名归档）
│   ├── run_hyperopt.sh          # 仅样本内 hyperopt（seed=42）
│   ├── run_walkforward.sh       # 滚动窗口验证（冻结参数）
│   ├── stress_test.py           # 参数扰动/延迟入场/随机跳过
│   ├── funding_adverse_test.sh  # 资金费率×2 压力
│   ├── summarize_results.py     # 汇总指标 → CSV/MD
│   └── data_quality_report.py   # 数据质量报告
└── user_data/
    ├── configs/config_futures.json
    ├── data/binance/futures/    # feather 数据（不入 git）
    ├── strategies/              # 策略 v1/v1b/v2/v2b/v3/v3b
    ├── backtest_results/        # 回测 zip（不入 git）
    ├── hyperopt_results/
    ├── logs/
    └── reports/                 # 全部报告（入 git）
```

## 3. 数据

- 交易对：`BTC/USDT:USDT`、`ETH/USDT:USDT`、`SOL/USDT:USDT`（按市值预选，非按表现挑选）
- 周期：5m / 15m / 1h / 4h / 1d
- 范围：上市日起至 2026-09-11（BTC 2019-09-10、ETH 2019-11-30、SOL 2020-09-14；**2019-01-01 起的更早数据在 Binance USDT 本位永续上不存在**——合约尚未上线，非下载缺失）
- 资金费率 + 标记价格：freqtrade 自动下载；SOL funding 因 WAF 403 改用 data.binance.vision 官方归档构建（`scripts/build_funding_from_vision.py`），并与 freqtrade 原生 BTC funding 交叉验证：重叠区间 7337 行 **0 差异**
- 数据质量：见 `user_data/reports/data_quality_report.md`（缺失 0、重复 0、空值 0，全部 UTC）

复现下载：

```bash
make download        # = scripts/download_data.sh 20190101 20260912
```

## 4. 回测成本模型（关键假设，全部写入配置）

| 项目 | 取值 | 依据/说明 |
|---|---|---|
| 手续费 | **0.05% taker 双边**（`backtesting.fee=0.0005`） | Binance 永续 taker 标准费率；策略全部用市价单，保守假设双边 taker（无 maker 返还） |
| 滑点 | 通过费率上浮建模 | freqtrade 2026.8 无独立滑点参数；压力测试以 `--fee 0.001/0.0015`（2x/3x）覆盖"费率翻倍+滑点翻倍" |
| 资金费率 | 真实历史逐 8h 计入 | 回测自动按持仓方向收付；压力测试做 funding×2 |
| 杠杆 | 固定 3x（isolated） | 策略 `leverage()` 返回 3；不超过协议上限 |
| 仓位 | 单笔风险 = 1% 权益 | `custom_stake_amount` 按 ATR 止损距离反推名义价值，上限 35% 权益保证金 |
| 初始资金 | 10,000 USDT | `dry_run_wallet` |
| 随机种子 | hyperopt `--random-state 42`；压力测试扰动 seed=42 | 写死在脚本 |

回测引擎语义：信号在 K 线 t 收盘计算，t+1 开盘成交；所有指标仅用已收盘 K 线（`process_only_new_candles=True`，Donchian 通道 `shift(1)`，无未来函数）。

## 5. 策略版本与迭代日志（每轮一个假设变更，git 历史可查）

| 版本 | 文件 | 核心逻辑 | 周期 | IS 2021-22 结果 | 结局 |
|---|---|---|---|---|---|
| v1 | `TrendBaselineV1.py` | EMA20/50 交叉 + EMA200 方向 + ADX；ATR 初始/追踪止损 + 时间止损 | 1h | -30.8%（成本吞噬） | 淘汰：结构性成本劣势 |
| v1b | `TrendBaselineV1b.py` | 同 v1，唯一变更：周期→4h | 4h | 默认 -6.2% → hyperopt 高原中位数参数 **+52.2%**（Sharpe 0.52，DD 14.6%） | **最终候选** |
| v2 | `DonchianBreakoutV2.py` | 96 根 Donchian 突破 + 4h EMA200 过滤 | 1h | -79.9% | 淘汰 |
| v2b | `DonchianBreakoutV2b.py` | 同 v2，周期→4h（过滤升为 1d EMA200） | 4h | -28.9% → hyperopt 全空间最优仍 -11.4% | **淘汰（无盈利参数区域）** |
| v3 | `TrendVolFundingV3.py` | v1 + 波动率分位带过滤 + funding 拥挤过滤 | 1h | -22.7% | 淘汰 |
| v3b | `TrendVolFundingV3b.py` | 同 v3，周期→4h | 4h | hyperopt +46.6%（高原 216/250 盈利） | 验证集 -5.3%，负于 v1b → 淘汰 |

**冻结参数（v1b）**：adx_min=17，atr_stop_mult=2.6，atr_trail_mult=4.2（=hyperopt 盈利 epochs 中位数，非单点最优；见 `reports/plateau_TrendBaselineV1b.md`）。

共同约束：禁止马丁格尔/加仓/网格（`position_adjustment_enable=False`）；每笔 ATR 止损；catastrophic stoploss -0.30；时间止损 28 天；单笔风险 1% 权益；杠杆固定 3x。

## 6. 验证结果总览与报告索引

| 阶段 | 窗口 | 关键结果 | 报告 |
|---|---|---|---|
| 样本内 IS | 2021-2022 | +52.2%，Sharpe 0.52，DD 14.6% | `reports/summary_is*.md`、`summary_frozen.md` |
| 验证集 VAL | 2023 | **+0.16%，Sharpe 0.00**（选择 v1b 胜出） | `reports/summary_frozen.md` |
| **样本外 OOS（仅一次）** | 2024-01→2026-09 | **+19.8%（年化+6.9%），DD 16.0%，Sharpe 0.21，PF 1.23，146 笔，0 爆仓** | `reports/summary_oos_final.md`、`curve_oos_TrendBaselineV1b.png` |
| Walk-forward | 9×6个月，2022H2→2026H2 | 5 胜 4 负，累计约 +2%，单窗 DD≤14% | `reports/summary_walkforward_TrendBaselineV1b.md` |
| 压力测试 | 2021-2023 | 费率×2/×3：+45.4/+39.9%；funding×2：+45.2%；延迟1/2根：+11.7/+13.3%；跳过10/20%：+8.1/**-2.1%**；扰动±10-20%：+5~+24%；BTC/ETH/SOL 单独：+1.8/+11.5/+35.8%；牛/熊/震荡：+41.7/+7.5/+0.2% | `reports/summary_stress_v1b_isval.md`、`summary_stress_extra_v1b.md` |
| 参数敏感性 | 250 epochs | 187/250 盈利（62%），高原成立 | `reports/plateau_*.md` |
| 未来函数检测 | 2022 | `lookahead-analysis` has_bias=**No** | 命令见本节末 |
| 数据质量 | 全样本 | 缺失0/重复0/空值0 | `reports/data_quality_report.md` |
| Dry-run | — | 未启动（候选未达门槛）；计划已备 | `reports/dry_run_plan.md` |
| **最终结论** | — | **不推荐进入 dry-run（Sharpe 0.21 远低于 1，验证集无优势，WF 胜负各半）** | `reports/final_conclusion.md` |

未来函数检测命令：
```bash
.venv/bin/freqtrade lookahead-analysis --userdir user_data \
  --config user_data/configs/config_futures.json \
  --strategy TrendBaselineV1b --timerange 20220101-20230101
```

> 2019-09→2020-12 保留为指标预热期，不计入任何评估窗口。
> WF 采用冻结参数滚动（未逐窗重优化）——文档化局限，见 final_conclusion.md。

## 7. 一键复现

```bash
make install          # 安装
make download         # 下载数据
make quality          # 数据质量报告
make is-backtests     # 样本内基线
make hyperopt-X       # 样本内调参（X=策略名）
make val-backtests    # 验证集
make walkforward-X    # walk-forward
make stress-X         # 压力测试
make oos-X            # 样本外（仅一次！）
```

手动等价命令示例（一切结果均可由此复现）：

```bash
.venv/bin/freqtrade backtesting \
  --userdir user_data --config user_data/configs/config_futures.json \
  --strategy TrendBaselineV1b --timerange 20210101-20230101 --export trades --cache none
```

## 8. 研究者偏差声明

- 策略设计者的先验知识（对 2021-2026 行业历史的了解）本身构成一种隐性泄漏，无法通过数据划分消除，结论中已计入该不确定性。
- 交易对按市值预选（BTC/ETH/SOL）而非全市场筛选，避免幸存者偏差；但"选择永续+主流币"本身仍是研究选择。
- 任何后续修改不得参考 OOS 结果（协议红线）；OOS 只跑一次。

## 9. 安全边界

- 本仓库默认 `dry_run: true`，无 API key，不连接实盘。
- 未经用户明确授权，绝不实盘下单。
