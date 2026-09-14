# research_deepen — 并行深化计划共享章程（2026-09-14 启动）

> 调度员（主会话）派出 6 个并行 agent，各自在自己的沙盒目录工作。
> 本文件是所有 agent 的**必读前置**：环境事实、数据纪律红线、工程规范。

## 0. 环境事实（Windows 10 / Git Bash）

- 仓库根：`D:\Code\AIQuant\freqtrade-futures-lab`（bash 路径 `/d/Code/AIQuant/freqtrade-futures-lab`）。所有命令先 `cd` 到仓库根。
- venv：Python 3.11.11 + freqtrade **2026.8** + ccxt 4.5.64。
  - bash 里用 `.venv/bin/freqtrade`、`.venv/bin/python`（有 shim，可用）；
  - 直接调用用 `.venv/Scripts/python.exe` / `.venv/Scripts/freqtrade.exe`；
  - Python 脚本内 subprocess 一律用 `sys.executable`，禁止硬编码 `.venv/bin/python`。
- 硬件：16C32T Ryzen 9 8940HX，磁盘余量 790GB。**每个 agent 内部并行回测进程上限 4**，避免 6 agent × N 进程互相践踏。
- 已有数据（`user_data/data/binance/futures/*.feather`）：
  - 12 币（BTC ETH SOL BNB XRP ADA DOGE AVAX LINK DOT LTC UNI）1h+4h，2020-09→2026-09-12，含 funding_rate + mark；
  - BTC/ETH/SOL 另有 5m/15m/1d（2019-09→2026-09-14）。
  - 注意：funding 文件是逐 8h 结算事件（freqtrade 下载为 1h 文件名但稀疏行）。
- 12 币配置模板：`user_data/configs/OPT7_config_12p.json`（MOT4、fee 0.0005、12 币白名单）。
- oss 策略目录：`user_data/strategies/oss/`（freqtrade 2026.8 不递归扫描，须 `--strategy-path`）。
- 结果 zip 归档的既有惯例：见 `scripts/opt7_s3_run.sh`（跑完 → 找最新 zip → **解包校验内嵌 strategy 名** → 改名移走）。

## 1. 数据纪律红线（违反 = 整个深化计划作废）

1. **一切回测/评估窗口必须 ≤ 2023-12-31**。2024-01-01 之后的数据是未来一次性 holdout，禁止以任何形式出现在结果表里（下载数据文件本身可以包含未来行，评估必须切片）。
2. 唯一例外：无。跨交易所稳健性也只用 2021-2023。
3. 已冻结参数的策略复跑不算"调参"；任何新参数选择只能用 2021-2022（IS），2023 只允许按预注册规则做一次 VAL 判定。
4. 结论必须打标签：**[推断强化]**（对冻结结果的更严格统计）/ **[稳健性]**（新轴复验）/ **[假设生成]**（烧毁窗口上的探索，待新数据验证）。验证级结论只能来自未来数据。

## 2. 工程规范

1. **沙盒隔离**：只写 `research_deepen/<你的名字>/` 下的子目录（results/ scripts/ strategies/ configs/ reports/ 已建好）。禁止修改仓库任何既有文件（含 user_data/strategies、configs、reports、scripts）。读取不受限。
2. 新策略文件放自己的 `strategies/`，回测加 `--strategy-path research_deepen/<name>/strategies`。策略类名加自己的前缀（见各 agent 章程），保证并行时 zip 内容可区分。
3. **zip 卫生**：每次回测后立即把 `user_data/backtest_results/backtest-result-*.zip` 中内嵌 strategy 名等于你类名的最新一个，改名移入自己的 `results/`。绝不留无名 zip 在公共目录。
4. 禁止 `git commit/push`；禁止安装包进主 `.venv`（需要额外依赖→建自己的 uv venv）。
5. 长命令后台跑 + 轮询（经验教训：前台 10 分钟无输出会被超时杀掉，phase7 的 S4 事故）。
6. 诚实优先：负结果照报，禁止只挑好数字。

## 3. 交付物

每 agent：`research_deepen/<name>/report.md`（中文），必含：
- 方法（含为什么这样做统计上是对的）
- 关键数字表（含置信区间/分布分位数，能给就给）
- 局限与诚实披露
- 结论 + 级别标签
- 复现命令清单（从裸仓库到你的结果）

调度员最后汇总为 `research_deepen/MASTER_REPORT.md`。
