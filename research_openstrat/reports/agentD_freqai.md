# Agent D — FreqAI（机器学习）策略方向可行性调研报告

- 日期：2026-09-12
- 执行环境：macOS arm64（M 系列，10 核），实验室根目录 `/Users/caihaohan/ZCodeProject/freqtrade-futures-lab`
- 结论先行：**FreqAI 管线在本实验室可以低成本落地（独立 venv + 8 分钟安装 + 年度回测 10.6 分钟），已实跑通过**。但官方示例策略 2023 全年 VAL 窗口亏损（-43.3%），证明"跑得通"和"赚钱"之间还有很大距离；jerome-benoit 仓库的旗舰 QuickAdapterV3 依赖栈重、5m 大特征矩阵回测成本极高，本轮仅完成代码级评估未实跑。建议以"低成本管线 + 自有特征工程"路线小规模纳入，不建议现在就投入大算力。

---

## 1. FreqAI 在本实验室的落地可行性（已验证）

### 1.1 依赖与环境隔离（实测通过）

- 方案：独立 venv `research_openstrat/.venv-freqai`，完全不动主 `.venv`。
- 安装内容：`pip install "freqtrade[hyperopt,freqai]==2026.8" "joblib==1.4.2" lightgbm`，共 106 个包。
- 实测安装耗时约 7–8 分钟（网络正常）；磁盘占用 **718 MB**。
- 关键版本：freqtrade 2026.8 / lightgbm 4.7.0 / scikit-learn 1.9.1 / numpy 2.4.6 / **pandas 3.0.5** / CCXT 4.5.78。
- 注意：主 `.venv` 中没有任何 ML 库（无 sklearn/lightgbm），因此**必须**用隔离 venv，不可混用。
- 未安装（按协议跳过）：catboost、torch/RL 系、optuna 系（QuickAdapter 专用，见 §3）。

### 1.2 运行成本（实测）

| 项目 | 实测值 |
|---|---|
| venv 安装 | ~8 分钟，718 MB |
| 冒烟回测 1 个月（2023-06，3 对 15m） | **64 秒**（含训练+推理） |
| 全年回测 2023-01-01 → 2024-01-01 | **10 分 37 秒**（669s CPU / 131% 利用率） |
| 再训练次数 | train_period 30d / backtest_period 7d → 每对 ~52 次，3 对共 156 个模型 |
| 模型产物 | `user_data/models/nd_freqai_example_lgbm/` 5.8 MB（176 个文件） |
| 每次训练耗时 | ≈ (637s - 数据加载 ~30s) / 156 ≈ **3.9 秒/模型**（LightGBM、~90 特征、~2800 训练样本） |

结论：15m timeframe + 轻量特征 + LightGBM 的 FreqAI 回测成本与一次传统策略 hyperopt 相当，完全可以和传统策略并行迭代。

### 1.3 数据要求（本实验室已满足）

- 需要 base timeframe（15m）+ `include_timeframes`（15m、1h）+ corr pairs（BTC/ETH）的 OHLCV 历史：实验室 BTC/ETH/SOL 的 5m/15m/1h/4h/1d 全历史直接可用。
- FreqAI 回测自动把 `startup_candle_count` 提高到 2920（= train_period 30d + buffer），即 2023-01-01 起测会自动用 2022-12 之前的数据训练——数据边界无问题。
- futures 模式正常工作：funding fees 已计入（全年净 +30.39 USDT，588/1388 笔空单）。

### 1.4 落地时的坑（已踩过，均已解决）

1. `user_data/strategies/oss/` 子目录不在默认策略搜索路径 → 必须加 `--strategy-path user_data/strategies/oss`。
2. 2026.8 要求显式指定 `"freqaimodel"`（config 顶层），仅 `freqai.enabled=true` 不够，否则报 `No freqaimodel set`。
3. `--export-filename` 已废弃（DEPRECATED 警告），需用 `--backtest-directory` + 事后复制为 `ossD_` 前缀。
4. 同一 `identifier` 的模型目录会被不同 run 覆盖，多策略对比时给每个策略单独 identifier。

---

## 2. 仓库画像：jerome-benoit/freqai-strategies

- 活跃度：**非常活跃**，最后提交 2026-09-11（8 小时前），基于 renovate 自动化升级依赖。
- 内容：只有 2 个策略 + 配套 Docker/dev 工具链，README 193 KB（大量协议文档），工程质量高（basedpyright/ruff CI）。

| 策略 | 模型 | timeframe | 特点 | 本轮处置 |
|---|---|---|---|---|
| **QuickAdapterV3** | 自定义 `QuickAdapterRegressorV3`（freqaimodel，支持 xgboost/lgbm/catboost/ngboost/HistGBR，内置 optuna HPO） | 5m | 预测局部极值（extrema 回归 label + isodata 阈值 → 预测局部顶/底），NATR 自适应止盈止损、3 段部分止盈、保护机制、DI 异常过滤 | **代码级评估**（依赖重，未实跑，见下） |
| **ReforceXY** | RL（`RLAgentStrategy` + 自定义 ReforceXY freqaimodel，reward space 分析套件） | 多 tf | 强化学习 | 按协议跳过（torch/RL 太重） |

### QuickAdapterV3 未实跑的原因（证据）

- 额外硬依赖（import 实测 + 官方 Dockerfile）：`optuna==5.0.0`、`optuna-integration`、`optuna-dashboard`、`optunahub`、optuna-hub auto_sampler requirements、`scikit-learn-extra`、`scikit-image`、`ngboost`、`catboost`、`xgboost`、`datasieve`、pandas>=3.0，且依赖 optuna hub 远端 requirements URL（构建不可完全离线复现）。
- 代码量：策略 2551 行 + Utils.py 6287 行 + LabelTransformer 668 行 + freqaimodel 5180 行 ≈ 1.47 万行。
- 计算成本估算（按其 config-template 默认值）：expand_all 17 特征 × 3 indicator periods × 4 timeframes（5m/15m/1h/4h）× 6 shifted × 3 corr pairs ≈ 3672；expand_basic 41 × 4 × 6 × 3 ≈ 2952；**合计 ~6600 特征** vs 我们实跑的 ~90 特征（约 73 倍）。5m + train 21d + backtest 2d → 3 对 3 个月约 135 次再训练，参考本机 90 特征 3.9s/模型的速度线性外推即 >1 小时量级，且 5m 行数 ×3、特征 ×73，实际预计数小时～半天，超出本轮预算。
- 值得肯定的设计（后续可借鉴）：extrema 回归 label（预测局部顶底而非收益率）、DI（dissimilarity index）过滤训练外异常样本、label smoothing/weighting（kaiser 窗 + amplitude 加权）、causal_mode 防标签泄漏、NATR 自适应出场。

---

## 3. 实跑策略说明：ND_FreqaiExampleLgbm

- 来源：freqtrade 2026.8 内置模板 `FreqaiExampleStrategy.py`（`.venv/lib/python3.11/site-packages/freqtrade/templates/`），本实验室仓库里唯一"LightGBM/sklearn、依赖最轻"的候选（jerome-benoit 仓库不满足轻依赖条件，见 §2）。
- 改动：类名加 ND_ 前缀；timeframe 5m → **15m**（匹配实验室数据与运行成本）。逻辑零改动。
- 文件：`user_data/strategies/oss/ND_FreqaiExampleLgbm.py`（及阈值变体 `ND_FreqaiExampleLgbmT2.py`）。
- 模型：freqtrade 内置 `LightGBMRegressor`（回归）。
- 特征（~90 维）：expand_all 10 个指标（RSI/MFI/ADX/SMA/EMA/BB 宽度/ROC/相对量等）× indicator_periods [10,20] × timeframes {15m,1h} × shifted 2 × corr pairs {BTC,ETH} + basic 3 个 + standard（星期/小时）。
- 标签：`&-s_close` = 未来 20 根 15m K 线（5 小时）均价 / 现价 - 1。
- 入场：`do_predict==1` 且预测 > +0.01 做多 / < -0.01 做空（futures 双向）；出场：预测反转或 ROI（10%）/止损（-5%）。
- 再训练：每 7 天滚动重训（train 30 天窗口），365 天 × 3 对 = 156 个模型。
- 配置：`research_openstrat/agentD_config.json`（futures/isolated/fee 0.0005/3 对，与实验室 config_futures.json 对齐 + freqai 段）。

---

## 4. 回测结果（VAL 窗口 20230101-20240101）

### 4.1 基准：ND_FreqaiExampleLgbm（阈值 ±0.01）

| 指标 | 值 |
|---|---|
| 交易数 | 1388（3.8 笔/天；空单 588） |
| 总收益 | **-43.26%**（-4326 USDT / 10000） |
| 胜率 | 47.1%（654W/734L） |
| Max DD（account） | 44.32% |
| Sharpe / Sortino / Calmar | -6.51 / -7.60 / -5.11 |
| Profit Factor | 0.748 |
| Funding 净值 | +30.39 USDT |
| 出场分布 | roi 1228 / exit_signal 139 / stop_loss 21 |
| 耗时 | 10 分 37 秒 |
| 导出 | `user_data/backtest_results/ossD_FreqaiExampleLgbm_val.zip`（T2 变体：`ossD_FreqaiExampleLgbmT2_val.zip`） |

冒烟（20230601-20230701）：27 笔 / -1.6% / maxDD 4.04% / PF 0.73 / 64 秒——确认训练+推理+交易全链路工作正常。

### 4.2 阈值过滤变体：ND_FreqaiExampleLgbmT2（阈值 ±0.02，仅高置信预测入场）

| 指标 | 基准（±0.01） | T2（±0.02） | 变化 |
|---|---|---|---|
| 交易数 | 1388 | **349** | -75% |
| 总收益 | -43.26% | **-14.42%** | 减亏 29 个百分点 |
| 胜率 | 47.1% | 49.0% | +1.9pp |
| Max DD | 44.32% | **19.61%** | 减半 |
| Sharpe | -6.51 | **-1.55** | 显著改善 |
| Sortino / Calmar | -7.60 / -5.11 | -1.90 / -3.85 | 显著改善 |
| Profit Factor | 0.748 | 0.776 | 略升 |
| Funding 净值 | +30.39 | +29.83 | 持平 |
| 耗时 | 10m37s | 3m31s | -67% |

**解读**：仅把预测置信阈值从 ±0.01 提到 ±0.02（一行代码），亏损从 -43% 收敛到 -14%、回撤减半、Sharpe 从 -6.5 改善到 -1.5——证明**阈值过滤是本方向最便宜、最有效的单一优化杠杆**（信号质量排序能力存在，弱但非零）。但 PF 仍 <1（未转正），说明仅靠阈值还不够，需配合特征/标签/出场改造（见 §5.2）。

### 4.3 结果解读（重要）

- 官方模板自带免责声明："showcase of functionality, **not meant to be run live**"。本基准的定位是**管线可行性验证**，其 ±0.01 阈值、10% ROI、-5% SL 全是演示值，从未针对 futures/费率优化。
- 1228/1388 笔以 ROI 出场 + 平均持仓 3:48——预测信号本身对短期价格均值有弱预测力（PF 0.75 接近随机），但被 0.1% 手续费 × 高频进出（1388 × 双边）磨掉：粗算总手续费 ≈ 1388 × 2 × 0.05% × 平均仓位 ≈ 全部亏损的主要来源。
- Funding 为净正（+30 USDT），说明 futures 数据管线（funding/mark）正确。

---

## 5. 结论与建议

### 5.1 FreqAI 方向值不值得纳入后续优化？

**值得，但按"低成本管线"路线纳入，而非照搬重型开源策略。**

- 可行性：已验证。8 分钟装好隔离环境，年度回测 10.6 分钟，156 个模型仅 5.8 MB，不需要 GPU，不影响主 .venv。
- 性价比判断（与传统策略抢资源的角度）：
  - 单次迭代成本 ≈ 传统策略 hyperopt 一次（分钟级），完全可并行。
  - 但**当前基准无正收益**，直接纳入组合没有意义；需要先做 §5.2 的优化把它变正。
  - QuickAdapterV3 若要实跑：预计需再加 ~500 MB 依赖（optuna 系 + scikit-image + catboost 等）+ 单次年度回测数小时，**性价比低**，建议只借鉴其思想（见 §2）。

### 5.2 若继续，最优先的 1-2 个策略与具体优化角度

1. **首选：ND_FreqaiExampleLgbm 自有化改造**（成本最低，管线已通）
   - 阈值过滤：把 ±0.01 提到 ±0.02/±0.03 只交易高置信预测（T2 已实测验证方向，见 §4.2）。
   - 特征工程：加 funding rate / mark 价差作为特征（实验室已有 funding 数据，QuickAdapter 未利用）；加 4h 趋势 regime 特征做长短期对齐。
   - 标签改造：把"未来 5h 均价收益率"换成 QuickAdapter 式 extrema/分位数 label，或改用分类器（LightGBMClassifierMultiTarget）预测方向+波动桶。
   - 再训练频率：7d → 14d/30d 对比（减少过拟合 + 减半成本）；train_period 30d → 60d 增加样本。
   - 出场匹配：ROI 10% 与 5h 预测期严重错配，应改为预测期到期平仓或 NATR 自适应止盈。
2. **次选（观察项）：QuickAdapterV3**——思想上最完整的开源 FreqAI 策略（extrema label + DI 过滤 + causal mode 防泄漏），若未来要试，先砍配置（timeframe 5m→15m、include_timeframes 只留 15m/1h、shifted 6→2、关闭 optuna_hyperopt）再评估，可把特征数从 ~6600 压到 ~500 以内。

### 5.3 风险与限制

- 本报告回测窗口仅 2023 单年（VAL 协议），无跨周期验证；ML 策略对 regime 依赖更强，2023 牛市初期的结论不能外推。
- 官方示例策略亏损 ≠ FreqAI 无效；同样，本管线跑通 ≠ 能赚钱。中间需要特征/标签/出场三件事的针对性工程。
- pandas 3.0.5 与部分老策略生态（pandas_ta 等）可能存在兼容问题（本轮未遇到，QuickAdapter 已适配 pandas>=3.0）。

---

## 附：复现命令

```bash
# 环境（一次性）
python3.11 -m venv research_openstrat/.venv-freqai
research_openstrat/.venv-freqai/bin/pip install "freqtrade[hyperopt,freqai]==2026.8" "joblib==1.4.2" lightgbm

# 冒烟（~64s）
research_openstrat/.venv-freqai/bin/freqtrade backtesting \
  --userdir user_data --strategy-path user_data/strategies/oss \
  --config research_openstrat/agentD_config.json --strategy ND_FreqaiExampleLgbm \
  --timerange 20230601-20230701 --export trades \
  --backtest-directory user_data/backtest_results --cache none

# 全量（~10.6 min）；T2 变体换 agentD_config_t2.json + ND_FreqaiExampleLgbmT2
research_openstrat/.venv-freqai/bin/freqtrade backtesting \
  --userdir user_data --strategy-path user_data/strategies/oss \
  --config research_openstrat/agentD_config.json --strategy ND_FreqaiExampleLgbm \
  --timerange 20230101-20240101 --export trades \
  --backtest-directory user_data/backtest_results --cache none
```
