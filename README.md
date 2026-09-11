# freqtrade-futures-lab

本地 Freqtrade 加密永续合约（USDT-M Perp）回测研究系统。目标不是"稳定赚钱"，而是**过程严谨、结果可复现、风险透明**的策略研究流水线与候选策略结论。

> ⚠️ 免责声明：本仓库不包含任何盈利承诺。回测存在固有局限（执行假设、研究者先验、市场结构变化）。所有结论以证据为准，样本外失败就写失败。

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

## 5. 策略版本与迭代日志（每轮一个假设变更）

| 版本 | 文件 | 核心逻辑 | 周期 | 状态 |
|---|---|---|---|---|
| v1 | `TrendBaselineV1.py` | EMA20/50 交叉 + EMA200 方向 + ADX 过滤；ATR 初始/追踪止损 + 时间止损 | 1h | IS 基线：亏损（见报告） |
| v1b | `TrendBaselineV1b.py` | 同 v1，唯一变更：周期 1h→4h（降频摊成本） | 4h | — |
| v2 | `DonchianBreakoutV2.py` | 96 根 Donchian 突破 + 4h EMA200 方向过滤；ATR 止损 | 1h | IS 基线：亏损 |
| v2b | `DonchianBreakoutV2b.py` | 同 v2，唯一变更：周期 1h→4h（趋势过滤相应升为 1d EMA200） | 4h | — |
| v3 | `TrendVolFundingV3.py` | v1 核心 + ATR 分位数波动率带过滤 + 资金费率拥挤过滤 | 1h | IS 基线：亏损（但最轻） |
| v3b | `TrendVolFundingV3b.py` | 同 v3，唯一变更：周期 1h→4h（波动率窗口换算为 180×4h） | 4h | — |

共同约束：禁止马丁格尔/加仓/网格（`position_adjustment_enable=False`）；每笔 ATR 止损； catastrophic stoploss -0.30（价格口径）；时间止损 21-28 天。

## 6. 验证协议与报告索引

| 阶段 | 时间窗 | 报告 |
|---|---|---|
| 样本内 IS | 2021-01-01 → 2022-12-31 | `reports/summary_is*.md` |
| 验证集 VAL | 2023-01-01 → 2023-12-31 | `reports/summary_val*.md` |
| Walk-forward | 训练 2y / 测试 6m 滚动（冻结参数，不做逐窗调参——文档化局限） | `reports/summary_walkforward_*.md` |
| 压力测试 | 参数扰动 ±10%/±20%、延迟 1-2 根入场、随机跳过 10%/20%、费率 2x/3x、funding×2、分交易对、分牛熊震荡段 | `reports/summary_stress_*.md` |
| 样本外 OOS | 2024-01-01 → 2026-09-11，**仅一次** | `reports/summary_oos*.md` |
| 最终结论 | — | `reports/final_conclusion.md` |
| Dry-run 计划 | ≥4-8 周 | `reports/dry_run_plan.md` |

> 2019-09→2020-12 保留为指标预热期，不计入任何评估窗口。

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
