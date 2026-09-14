# XEX 跨交易所稳健性报告 — OPT4_VolatilitySystem 于 Bybit / OKX（2021-2023）

> 结论级别：**[稳健性]**（新轴复验：同样的 2021-2023 市场 regime，换一家交易所的撮合与数据）。
> 跨所**不是处女 OOS**：窗口与 Binance 冻结基线完全重叠，参数零改动零重选——本报告检验的是
> "edge 是否依赖 Binance 微结构特产"，不引入任何新检验自由度。
> 评估窗口纪律：所有结果 ≤ 2023-12-31（数据文件含 2024 后下载器补齐的行，评估切片严格切割；
> 详见 §6.4 边界 force-exit 说明）。

## 0. 一句话结论

**edge 不是 Binance 特产**：同一策略零改动在 Bybit 上 +507.2%（基线的 34%）、OKX 上 +1235.7%
（基线的 83%），三所逐笔经济学几乎无衰减（PF 保留 97-98%），逐币利润排序高度一致
（Spearman 0.66-0.94）。利润总量的差异主要来自 Bybit 2021 年上市窗口缺失与复利路径，
而非 edge 消失——2022-2023 全币共同窗口内三所逐笔 PF 分别为 1.64 / 1.73 / 1.63，无法区分。

## 1. 方法

- **策略**：`XEX_OPT4_BY` / `XEX_OPT4_OK`（`research_deepen/xexchange/strategies/`），纯子类
  `pass`，仅加 sys.path 指向 `user_data/strategies/oss` 并使用独立类名以便 zip 归属。冻结参数
  2.0/2.0（signal/stop ATR 倍数）、atr08 门（0.8×30d 中位）、60d 时间止损、1% 风险、2x、MOT4。
- **数据**：`freqtrade download-data`，bybit/okx 期货（USDT 永续、isolated 口径）、12 币白名单同
  `OPT7_config_12p.json`、feather、1h、20200901-20240101。两所 1h K 线**零缺口**。
- **回测口径**：timerange 20210101-20240101（与冻结基线完全一致）、fee 0.0005 统一、市场单
  （taker 双边）、futures/isolated、起始 10000 USDT。Binance 基线直接引用冻结数字
  （`opt4_C2_12p_mot4_is.zip`：+1495.8% / DD 15.92% / Sharpe 1.01 / PF 1.97 / 433 笔 / 0 爆仓）。
- **统计上为什么这样比是对的**：
  - 组合级利润%是复利路径依赖量，跨所比较会被"早期收益放大后期仓位"污染；因此**主判据用
    scale-free 指标**：逐笔 profit-factor（PF）、胜率、逐币利润排序的 Spearman 相关、出场原因
    分布、逐年/半年度 PF。利润%仅作总量参考并给出归因分解。
  - 两所数据是同一 underlying 市场的不同观测（相关性极高），不是独立样本——所以结论措辞是
    "edge 迁移/衰减"，不是"独立复制"。
  - 参数在 Binance 2021-2023 上冻结后零改动跨所，无调参风险；对照数字全部来自冻结 zip 内
    trades 导出，同一段代码同口径计算。

## 2. 关键数字：三所对照（2021-01-01 → 2024-01-01，fee 0.0005）

| 指标 | Binance（冻结基线） | Bybit（本次） | OKX（本次） |
|---|---|---|---|
| 总利润 % | **+1495.8%** | **+507.2%** | **+1235.7%** |
| 利润保留率 | — | 33.9% | 82.6% |
| CAGR % | 151.8 | 82.4 | 137.3 |
| Max DD（account） | 15.92% | 16.67% | 19.81% |
| Max % underwater | —（冻结未载） | 27.28% | 19.81% |
| Sharpe（closed） | 1.01 | 0.90（保留 89%） | 0.95（保留 94%） |
| Profit factor | 1.97 | 1.91（保留 97%） | 1.94（保留 98%） |
| 交易数 | 433 | 425（98%） | 432（99.8%） |
| 胜率 | 31.9%（138W/295L） | 29.4%（125W/300L） | 29.4%（127W/305L） |
| 均笔均值 p 值 | —（冻结未载） | 0.0126 | 0.0095 |
| 爆仓 | 0 | 0 | 0 |
| 多/空 利润贡献 | — | +379.2% / +128.0% | +906.6% / +329.1% |
| 出场原因分布 | stop 63.3% / signal 34.9% / time 0.9% / force 0.9% | 65.2 / 33.4 / 0.5 / 0.9 | 65.0 / 33.3 / 0.7 / 0.9 |
| 市场变化（买入持有参照） | +906.5% | −26.63% | +575.1% |

三所结构指纹几乎相同：交易数 425/432/433、胜率 29-32%、止损出场占比 63-65%、时间止损 <1%、
零爆仓、多头主导利润——**同一策略机制在三套数据上同构运行**。两所均笔均值 t 检验 p<0.013，
独立于 Binance 仍显著为正。

### 2.1 真实费率敏感性

- 查证（2026-09）：Bybit 永续非 VIP **taker 0.055%**（[Bybit 费率页](https://www.bybit.com/en/help-center/article/Trading-Fee-Structure)）；
  OKX 永续基础档 **taker 0.05%**（[OKX 费率页](https://www.okx.com/en-us/fees)）——OKX 与统一
  口径 0.0005 完全相同，无需单独跑；Bybit 加跑 fee 0.00055。
- 结果：+513.4% / DD 16.51% / Sharpe 0.91 / PF 1.92，交易集与 0.0005 跑完全相同（425 笔、
  胜率 29.4%）。10% 的费率上浮对结果无实质影响（与冻结报告 fee×3 保留 81% 的结论一致；
  绝对利润的 ±1% 波动是 1% 风险模型下权益路径复利噪声，非费率效应）。

## 3. 逐币对照（利润 %，2021-2023）

| 币 | Binance | Bybit | OKX | Bybit 上市 | OKX 上市 |
|---|---|---|---|---|---|
| AVAX | +471.2 | +166.3 | +419.9 | 2021-09-15 | 2020-09-23 |
| SOL | +406.7 | +131.5 | +340.0 | 2021-10-15 | 2021-01-22 |
| BNB | +227.8 | +47.0 | +79.0 | 2021-06-29 | **2022-12-23** |
| ETH | +154.2 | +84.2 | +153.1 | 2021-03-15 | 全窗口 |
| BTC | +152.6 | +27.4 | +70.6 | 全窗口 | 全窗口 |
| XRP | +82.9 | +5.3 | **−48.0** | 2021-05-13 | 全窗口 |
| DOT | +70.8 | +21.2 | +60.3 | 2021-03-18 | 全窗口 |
| LTC | +25.7 | −4.3 | +48.1 | 2020-10-21 | 全窗口 |
| ADA | −4.6 | −2.6 | +44.5 | 2021-03-18 | 全窗口 |
| DOGE | −9.8 | −14.6 | −24.7 | 2021-06-02 | 全窗口 |
| UNI | −39.5 | −5.8 | −51.3 | 2021-11-30 | 2020-09-17 |
| LINK | −42.5 | **+51.7** | **+144.1** | 全窗口 | 全窗口 |

- 逐币利润排序 Spearman：Bybit vs Binance **0.71**（p=0.009）、OKX vs Binance **0.66**（p=0.018）、
  Bybit vs OKX **0.94**（p<0.001）。核心盈利源（AVAX/SOL/ETH）三所全部为正且排序一致；
  单币翻转（LINK 三所 −43/+52/+144，XRP +83/+5/−48）在每币仅 15-59 笔的样本量下属预期 dispersion。
- Binance 12 币自 2020-09 起全有数据；Bybit 8/12 币晚上市 3-14 个月；OKX 仅 BNB（2022-12）与
  SOL（晚 4.5 个月）受限。上市窗口差异 → 三所实际可交易宇宙不同，见 §5 归因。

## 4. 半年度逐笔 PF（scale-free 主判据）

| 半年 | Binance | Bybit | OKX |
|---|---|---|---|
| 2021H1 | 2.31 | **0.33** | 2.60 |
| 2021H2 | 1.54 | 1.22 | 1.45 |
| 2022H1 | 2.22 | 2.17 | 2.12 |
| 2022H2 | 2.04 | 1.85 | 1.53 |
| 2023H1 | 1.47 | 1.58 | 1.75 |
| 2023H2 | 1.75 | 2.18 | 1.97 |

Bybit 唯一负半场是 2021H1（PF 0.33）——恰是其宇宙仅 3-11 币的时段；自 2021H2 起六个半年带
三所逐笔 PF 完全同带。OKX 全程贴合 Binance。

## 5. "数据源差异" vs "edge 不存在"的区分

1. **edge 存在于两家独立于 Binance 的数据源**：OKX 2021 逐笔 PF 2.15（B 2.02）、全窗口利润保留
   83%、逐币排序 ρ=0.66。若 edge 是 Binance 数据特产，OKX 不应复现。
2. **Bybit 的 −66% 利润缺口可分解**（非复利、逐年 sumPnL，USDT）：
   - 2021：B 19,932 vs BY 880 —— **上市窗口是主因**：Bybit 2021 大部分时间只有 3-9 币可交易
     （ETH 3 月、XRP 5 月、SOL 10 月才上市），错过了 Binance 基线 2021 年（牛市主升段）的
     主要盈利宇宙；且 2021 权益基数小，后续复利起点低。
   - 2022：B 33,278 vs BY 9,474；2023：B 53,156 vs BY 24,390 —— 共同窗口内缺口仍在但大幅收窄，
     且逐笔 PF（2022：2.00 vs 2.12；2023：1.81 vs 1.58）**无劣势**。剩余缺口主要是复利路径：
     Binance 携 2021 的 2 倍权益进入 2022。
   - 匹配币对照（BTC/LINK/LTC，三所全窗口上市，2021 年关闭交易）：B sum_pr +126.8%（PF 1.62）
     vs BY −214.1%（PF 0.62）vs OK +101.4%（PF 1.48）。Bybit 2021 即便在可交易的币上逐笔也差
     ——这是真实的"数据源差异"成分（撮合/蜡烛形态/ATR 止损触发差异，或 n=50 小样本波动），
     但它被 OKX 的正常表现证明**不是 edge 本身失效**。
   - 2022-2023 全币共同窗口逐笔 PF：B 1.64 / BY 1.73 / OK 1.63 —— 三所不可区分。
3. **结论**：可区分。证据结构是"逐笔经济学跨所保留（PF 97-98%）、机制同构（交易数/胜率/出场
   分布）、逐币排序一致（ρ≥0.66）、独立第二所 OKX 全面复现"，而差异集中在 Bybit 特定的
   2021（上市窗口 + 该所早期数据特征）。判定：**edge 普适，利润总量衰减主要来自窗口/复利，
   非微结构特产；Bybit 2021H1 为唯一未完全归因的反例半场，如实保留**。

## 6. 披露与局限

1. **OKX funding 未计入（定量）**：OKX funding 端点只返回最近 100 条（2026-06→07），无法回溯
   2021-2023；回测日志确认 "No history for … funding_rate found"，trades 导出 funding_fees 合计 0。
   影响：funding 是该策略的成本项——Binance 基线 −5,362 USDT（利润的 −3.6%）、Bybit −2,236
   （−4.4%）。故 **OKX +1235.7% 被高估约 3.5-4.5%（相对值）**，方向一致、量级不改变任何结论。
   Bybit funding/mark 自上市日全覆盖，真实计入。
2. **窗口纪律**：下载数据文件含 2024-01 之后行（下载器补齐行为，CHARTER 允许）；回测
   --timerange 20240101 截止。trades 里 close_date=2024-01-01 00:00:00 的 4 笔是**边界
   force_exit 记账戳**（2023-12-31 23:00 前的价格强平仓），Binance 冻结基线含同样 4 笔，三所
   同口径（每所各 4 笔、全部盈利、占比 <3% 利润）。2024 后无任何数据进入结果。
3. **跨所是稳健性轴**：2021-2023 与基线完全重叠，非 OOS；"验证级结论只能来自未来数据"不变。
4. **回测撮合假设**：1h K 线撮合、无滑点/深度/资金费率冲击建模，三所同样乐观；跨所相对比较
   不受影响，绝对数字照旧偏乐观。
5. **费率查证来源**：Bybit/OKX 官方费率页（链接见 §2.1）；普通用户档，未计 VIP/返佣。
6. **Bybit 2021H1**（PF 0.33）无法在现有数据内完全归因：候选解释为该所早期 USDT 永续的
   数据/微结构特征、3 币宇宙下 MOT4 槽位集中、以及小样本（44 笔）。未做任何事后修补。
7. **数据完整性**：两所 12 币 1h 零缺口；OKX mark 全覆盖、funding 仅近 100 条（见 1）。

## 7. 工程记录（复现要点）

- ccxt 4.5.64 的 bybit `fetch_leverage_tiers()`（批量分页）**随机丢符号**（实测 750/765，本任务
  丢 XRP/UNI → freqtrade 拒跑）。绕过：用单符号端点构建 freqtrade 标准缓存
  `user_data/data/bybit/futures/leverage_tiers_USDT.json`（脚本
  `research_deepen/xexchange/scripts/build_bybit_tiers_cache.py`，缓存 1 天有效，属 freqtrade
  官方缓存机制，未改任何仓库代码）。OKX 走逐符号慢路径无此问题。
- 结果 zip（已按内容校验归档至 `research_deepen/xexchange/results/`）：
  `xex_by_f0005_XEX_OPT4_BY.zip`、`xex_by_f00055_XEX_OPT4_BY.zip`、`xex_ok_f0005_XEX_OPT4_OK.zip`。
  公共目录未留本任务 zip。

## 8. 复现命令清单（裸仓库起）

```bash
cd /d/Code/AIQuant/freqtrade-futures-lab
# 1) 下载数据（两所，公开端点，无需 API key）
.venv/bin/freqtrade download-data --userdir user_data \
  --config research_deepen/xexchange/configs/bybit_fut.json \
  --timerange 20200901-20240101 --timeframes 1h
.venv/bin/freqtrade download-data --userdir user_data \
  --config research_deepen/xexchange/configs/okx_fut.json \
  --timerange 20200901-20240101 --timeframes 1h
# 2) 修 bybit leverage tiers 缓存（见 §7）
.venv/bin/python research_deepen/xexchange/scripts/build_bybit_tiers_cache.py
# 3) 回测（runner 自动做内容校验归档）
bash research_deepen/xexchange/scripts/xex_run.sh XEX_OPT4_BY \
  research_deepen/xexchange/configs/bybit_fut.json 20210101-20240101 by_f0005
bash research_deepen/xexchange/scripts/xex_run.sh XEX_OPT4_BY \
  research_deepen/xexchange/configs/bybit_fut.json 20210101-20240101 by_f00055 --fee 0.00055
bash research_deepen/xexchange/scripts/xex_run.sh XEX_OPT4_OK \
  research_deepen/xexchange/configs/okx_fut.json 20210101-20240101 ok_f0005
# Binance 基线：直接引用 user_data/backtest_results/opt4_C2_12p_mot4_is.zip（冻结）
```

日志：`research_deepen/xexchange/scripts/dl_{bybit,okx}.log`、`bt_*_XEX_OPT4_*.log`。

## 9. 结论

**[稳健性] OPT4_VolatilitySystem 的 edge 迁移到 Bybit 与 OKX**：零参数改动下两所 2021-2023
均显著为正（+507.2% / +1235.7%，均笔 p≤0.013），PF 保留 97-98%，Sharpe 保留 89-94%，DD 同带
（16.7%/19.8% vs 15.9%），零爆仓，出场机制同构。利润总量衰减（Bybit −66%、OKX −17%）经归因
主要来自 Bybit 2021 上市窗口缺失与复利路径；共同窗口（2022-2023）三所逐笔 PF 1.63-1.73 不可
区分，逐币排序跨所一致（ρ 0.66-0.94），独立第二所 OKX 全面复现——**支持"普适波动率突破
edge"而非"Binance 微结构特产"**。保留的反例：Bybit 2021H1（PF 0.33，匹配币亦弱）提示该所
早期数据/微结构存在真实差异成分；OKX funding 未计使其数字小幅高估 3.5-4.5%。验证级判断
仍需未来数据。

> 不构成投资建议。回测撮合假设下限数字，无实盘授权。
