# WS1 — AB 双 sleeve（BTC/ETH/SOL）动态调仓的最小可行运行资金

2026-11-03 · 数据：既有 3 币回测 zip（10,000 USDT 基钱包）+ 2026-11-03 实时拉取的 Binance USDT-M 限额。
未跑新回测；全部为分布统计 + 线性缩放推导。

## 结论（先读这个）

| 门槛 | 资金 C (USDT) | 含义 |
|---|---|---|
| **数学上能跑（机制完整）** | **≈1500** | 所有初始单过交易所限额、B 篮子 3 币完整建仓；接受 A 极端尾部（stop 最宽的少数交易）被 min-stake 向上 bump |
| 边界可跑（不推荐） | ≈1000 | B 的 BTC 初始单 88 vs 有效下限 80.6，余量仅 9%（BTC 涨到 ~89k 即失效）；A 有 1.5% 的 BTC 交易被 bump ≤40%；B 的 BTC 仓长期卡在目标权重的 ~74% |
| **sizing 失真 <10% 的严肃门槛** | **≈3500（当前价）；对 BTC 历史极价稳健需 ≈5500，取 5000 档** | BTC 0.001 步进使 p50 交易的 notional 截断误差 <10%（全步口径）+ B 补仓名义损耗 <10% |

- **主要元凶是 BTC 的 0.001 数量步进**：当前价 76,767 下每步 76.8 USDT 名义，比 BTC 自己的最小名义（50）还大。ETH（步 2.26 USDT）/SOL（0.92 USDT）在 C=1000 时误差已 <1.3%，可忽略。
- **回收系数 1.28/1.56 不改变 C_min**：它放大单笔 notional（更容易过限额），影响只在保证金并发（见下）。注意它只在 BTC<SMA100（B 空仓、36% 资金闲置）时生效，此时 A×1.56 的最坏保证金需求 = 总账户的 1.24 倍（历史仅 0.24% 的小时数），实现上只能放大**新仓**且受 available 约束——WS3 的实现约束，不是资金门槛。
- 费用与 funding 都是纯比例成本，无固定最低，对小资金无额外惩罚（量化见 §5）。
- **本次两份回测运行时在线加载了真实 markets 并强制了限额**（证据：B 的 ETH 补仓单最小 23.05 USDT = 20×1.1667−步进截断，BTC 补仓最小 48.3 同理）。所以"回测能跑"在这两份 zip 里已经隐含了交易所限额；但该限额是运行日快照，离线/缓存 markets 时 freqtrade 不强制——dry-run 与实盘的差异详见 §6。

---

## 1. 策略常数（代码实测）

`user_data/strategies/oss/OPT1_VolatilitySystem.py`（OPT4/DP_OPT4 原样继承，`DP_sleeves.py` 零改动）：

| 常数 | 值 | 作用 |
|---|---|---|
| `risk_pct` | 0.01 | 单笔风险 = equity × 1% |
| `leverage_fixed` | 2.0 | 固定 2x，margin = notional/2 |
| `stop_pct_floor` | 0.005 | stop 距离下限 0.5% |
| `margin_cap` | 0.35 | 单笔 margin ≤ 35% equity（即 notional ≤ 0.70×equity） |
| `stop_atr_mult` | 2.0（默认） | stop = 2 × 入场时重采样 ATR |

B sleeve（`NC_MomRegime15mFast.py` → OPT2/DP_SleeveB）：`TOP_N=3`，目标权重 pv/3；初始单 `min(proposed, target, 10%蜡烛成交量)`；补仓 `add = min(target−current, fillable, max_stake)`，`add < min_stake` 直接跳过；杠杆 1x；无显式 stoploss（freqtrade 默认 −0.10，进入 min_stake 储备计算）。

## 2. 实测分布（10,000 USDT 基钱包，20210101-20260912，3 币）

### 2.1 A sleeve（DP_OPT4 zip `backtest-result-2026-11-03_08-22-30.zip`，476 笔）

**注意**：trades JSON 的 `initial_stop_loss_abs` 记录的是 −0.30 灾难止损（2x 下恒 15% 价格距离），**不是** sizing 用的 stop；sizing stop 用 `stop_loss_abs`（custom_stoploss 的 ATR 锚定止损，无追踪、入场后不变）。

实际 sizing stop 距离（|open_rate − stop_loss_abs|/open_rate）：

| 币 | min | p5 | p50 | p95 | max | floor(0.5%)触发 |
|---|---|---|---|---|---|---|
| BTC (n=196) | 1.25% | 1.58% | 2.94% | 6.08% | 11.14% | 0 次 |
| ETH (n=160) | 1.31% | 1.78% | 3.55% | 7.01% | 12.92% | 0 次 |
| SOL (n=120) | 1.45% | 2.05% | 4.34% | 11.68% | 18.70% | 0 次 |

→ `stop_pct_floor=0.005` 在 3 币 2021-26 全样本从未触发（最窄 stop 1.25%）；有效分布 1.25%–18.7%。

单笔 notional 占 A equity 比例（= min(0.01/stop_pct, 0.70)，与实测 notional 吻合，median|err| 0.5pp）：

| 币 | min | p5 | p50 | p95 | max |
|---|---|---|---|---|---|
| BTC | 9.0% | 16.4% | 34.0% | 63.3% | 70%（cap，仅 5/476 笔触发） |
| ETH | 7.7% | 14.3% | 28.2% | 56.0% | 70% |
| SOL | 5.4% | 8.6% | 23.1% | 48.9% | 69.2% |

换算到任意 C：**单笔 notional = 上表比例 × (0.64·C)**，margin = 一半。
（参考：10k 基钱包的绝对值 BTC notional p50 37.9k / max 122k，含净值复合效应，勿直接引用。）

### 2.2 B sleeve（DP_SleeveB zip `backtest-result-2026-11-03_08-24-51.zip`，135 笔 / 404 张入场子单，其中 269 张补仓）

| 量 | 分布（占 B equity） |
|---|---|
| 初始单 notional | 极稳定 24.5–24.8%（p50 24.76%） |
| 补仓子单 notional | min 0.018% / p25 0.91% / p50 6.3% / p90 8.6% / max 20.2% |
| 单笔聚合（初始+补仓） | p50 33.3%（=目标 pv/3）, p95 41%（0.45 trim 上限附近） |
| 持仓时长 | p50 5d / p75 24.5d / 均值 18.2d / max 111d；≥18d 的 42 笔 |

换算到任意 C：初始单 ≈ 0.2476 × (0.36·C)；目标权重 0.333 × (0.36·C)。

**结构性缺口**：初始只建到目标的 74%，缺口 = (1/3 − 0.2476)×0.36·C = 0.0309·C。补仓要过 BTC 下限 80.6（见 §3）需要 **C ≥ 2611**；ETH/SOL 的下限低（23.3/5.8），C ≥ 754/188 即可补足。即 **C < 2611 时 B 的 BTC 仓会系统性停留在 ~74% 目标权重**（10k 基钱包实测：补仓单最小 14.8–48.3 USDT，p25 也只有 786，小 C 时大量被限额跳过）。

## 3. 交易所真实约束（2026-11-03 ccxt 直连实测，非文档值）

`.venv/Scripts/python.exe` + ccxt 4.5.64 **直连** fapi.binance.com 成功（无需代理；仓库存的 127.0.0.1:7897 代理本次未用到）：

| 币对 | minNotional | stepSize | minQty | tickSize | last price |
|---|---|---|---|---|---|
| BTC/USDT:USDT | **50** | 0.001 | 0.001 | 0.10 | 76,767.2 |
| ETH/USDT:USDT | **20** | 0.001 | 0.001 | 0.01 | 2,261.36 |
| SOL/USDT:USDT | **5** | 0.01 | 0.01 | 0.01 | 92.14 |

（RAW filters 已核对：MIN_NOTIONAL/LOT_SIZE/MARKET_LOT_SIZE 一致。与文档默认值的差异：BTC 实为 50 而非 ~100；ETH/SOL minQty 实为 0.001/0.01。）

**freqtrade 有效下限**高于交易所下限（`exchange.py _get_stake_amount_limit`：`max(minNotional×1.05/(1−|stoploss|), minQty×price×1.05) / leverage`）：

| 币 | A 有效 notional 下限（stoploss −0.30 → 储备 1.5） | B 有效下限（−0.10 → 1.1667） |
|---|---|---|
| BTC | max(75, 0.00105×P) = **80.6** @76.8k（126 @120k） | 同式 **80.6** @76.8k |
| ETH | **30.0** | **23.3** |
| SOL | **7.5** | **5.8** |

注意 BTC 下限由 **minQty×price** 主导，随币价线性上行：BTC=100k → 105；120k → 126。

## 4. C 档位 × 检查项矩阵

检查口径：notional = 实测比例 × C×0.64（A）/ ×C×0.36（B），当前价（BTC 76.8k）。
"A bump%" = 最小 notional 交易被顶到下限的放大倍数（bump 后单笔风险 >1% equity，语义失真）；
"BTC step err%" = 0.001×76767/notional，全步向下截断的最坏误差（期望约一半）。

| C | A BTC 最差单过下限 | A BTC bump 幅度 | **A BTC p50 粒度误差** | A ETH/SOL | B BTC 初始过下限 | B 补仓单被跳过（按笔/按名义） | 判定 |
|---|---|---|---|---|---|---|---|
| 500 | ✗ | +180%（24.5% 的 BTC 交易受影响） | 70% | ETH ✗ +21% | **✗ 无法建 BTC 仓** | 79% / 63% | 不可行 |
| 1000 | ✗ 尾部 | +40%（1.5% 交易） | **35%** | ✓ | ✓ 仅 9% 余量（BTC≥89k 失效） | 64% / 39% | 边界可跑 |
| 1500 | ✓ | 0 | 23% | ✓ | ✓ | 61% / 37% | **数学最小** |
| 2000 | ✓ | 0 | 18% | ✓ | ✓ | 57% / 34% | 能跑 |
| 3000 | ✓ | 0 | 11.8% | ✓ | ✓ | 38% / **8.6%** | B 补仓达标（C≥2611 后 BTC 可补足） |
| 5000 | ✓ | 0 | **7.0%** | ✓ | ✓ | 33% / 6.0% | **严肃门槛** |
| 10000 | ✓ | 0 | 3.5% | ✓ | ✓ | 23% / 2.6% | （基线回测即此档） |

精确阈值解：

| 约束 | 阈值 C |
|---|---|
| A BTC 最差单（notional frac 9.0%）≥ 80.6 | ≥ **1403**（BTC=120k 时 ≥ 2193） |
| A ETH / SOL 最差单 | ≥ 606 / ≥ 219 |
| B BTC 初始（0.2476×0.36C）≥ 80.6 | ≥ **915**（BTC=100k ≥ 1192；120k ≥ 1431） |
| B ETH / SOL 初始 | ≥ 262 / ≥ 65 |
| B BTC 首次补仓可行（结构性缺口 0.0309C ≥ 80.6） | ≥ **2611** |
| A BTC p50 粒度 <10%（全步） | ≥ **3524**（BTC=120k 时 ≥ 5560）；半步口径 ≥ 1762 |
| B 补仓名义损耗 <10% | ≥ ~2900 |

**BTC 步进是唯一的粒度问题**：C=1000 时 ETH p50 误差 1.25%、SOL 0.62%，均已达严肃标准；BTC 同档 35%。步进名义成本 = 0.001×P，随币价上行恶化（历史区间 16.7k→121.8k 对应 16.7→121.8 USDT/步）。

### 4.1 A 并发保证金利用率（含回收系数，规模不变量）

按逐小时 Σ(在场 stake)/A equity（A-only 回测净值轨迹；对 C 线性缩放不变）：

| 回收系数 | max | p99 | 超过 A 自己 wallet 的小时数 | 超过总账户 C 的小时数（B 空仓时） |
|---|---|---|---|---|
| ×1.00 | 1.246 | 0.955 | 0.24% | — |
| ×1.28 | 1.595 | 1.222 | 4.07% | 0.136%（max 1.021 C） |
| ×1.56 | 1.944 | 1.490 | 11.29% | 0.241%（max 1.244 C） |

解读：即便不回收，A 自身在净值回落后就存在 used margin > wallet 的小时（0.24%，此时无法开新仓直至平仓）；回收 ×1.56 把这个比例抬到 11.3%（对 A wallet 口径），但对总账户只有 0.24% 的小时数——因为回收生效时 B 的 36% 是空仓现金。**结论：回收系数不抬高 C_min，但 WS3 实现必须"只放大新仓、cap 到 available"，不能对存量仓乘系数**（最坏小时连总账户都差 24% 才够）。

## 5. 费用与 funding（纯比例，无固定最低）

- taker 0.05% 双边：Binance USDT-M 手续费率不设最低金额，确认小资金无额外惩罚。C=1000 时 A 单笔（p50 notional）：BTC 218 → 双边 **0.22 USDT**（= 该笔 1% 风险预算 6.4 USDT 的 3.4%）；ETH 0.18（2.8%）；SOL 0.15（2.3%）。比例恒定，与 C 无关。
- funding 对 B 长持仓（实测 `funding_fees/入场名义`，funding gate 0.0005/8h 生效下）：全部 135 笔中位 −0.11%；**≥18d 的 42 笔：中位 −1.38% / 均值 −4.82% / p95 −0.24%**（均值被 2021 牛市高 funding 拉偏）。参考：+0.01%/8h 持 18 天 = 名义的 0.54%。C=1000 时 B 每仓 ~120–180 USDT，一次 18d+ 持仓的典型 funding 成本 ~1.7–2.5 USDT。全部与 C 成比例。

## 6. freqtrade 层面：回测 / dry-run / 实盘的限额差异

- **回测**：若启动时能从交易所加载 markets（本次两份 zip 即如此，证据见 §2.2 的补仓下限痕迹），`custom_stake_amount` 收到的 `min_stake` 就是真实限额，策略的 bump/跳过逻辑照常生效，**且回测同样做步进向下截断**——所以小 C 的 sizing 失真（§4）在回测里就会真实发生，用 `dry_run_wallet=1000` 重跑即可复现。若离线/缓存无 markets 元数据，则完全不强制，"回测能跑"≠"实盘能成交"。
- **dry-run**：在线连交易所（公开端点即可），markets 实时加载，限额与步进**强制生效**——与实盘一致；差异仅在撮合假设（无真实盘口/滑点）。
- **实盘**：限额强制 + 真实盘口。小资金下 A 的 min-stake bump（`stake = max(stake, min_stake)`）会把尾部交易顶到下限之上，单笔风险突破 1% 语义——这是设计使然（OPT1 代码如此），不是 bug，但 C 小时更频繁触发。

## 7. 数据来源与复现命令

```
# 分布统计（A/B 两 zip → research_ab/results/ws1_*_dist.csv，日志 research_ab/logs/ws1_analysis.log）
.venv/Scripts/python.exe research_ab/scripts/ws1_analyze.py
# C 档位矩阵（→ research_ab/logs/ws1_matrix.log）
.venv/Scripts/python.exe research_ab/scripts/ws1_matrix.py
# 交易所限额实时核对（本次直连成功）
.venv/Scripts/python.exe -c "import ccxt,json; ex=ccxt.binanceusdm({'enableRateLimit':True}); \
  m=ex.load_markets(); print(json.dumps({s:{'minNotional':m[s]['limits']['cost']['min'], \
  'step':m[s]['precision']['amount'],'minQty':m[s]['limits']['amount']['min']} \
  for s in ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT']}, indent=1))"
```
输入 zip（未复制、原地读取）：`user_data/backtest_results/backtest-result-2026-11-03_08-22-30.zip`（DP_OPT4）、`..._08-24-51.zip`（DP_SleeveB）。本次未跑新回测，无新 zip。

## 8. 诚实披露

- **实测**：A stop/notional 比例分布（476 笔）、B 订单分布（404 子单）、并发保证金利用率、回测强制限额的证据、交易所限额与价格（2026-11-03 快照）。
- **线性缩放假设**：各 C 档的 notional = 实测比例 × C×0.64/0.36。隐含假设：信号与 stop 距离分布与资金规模无关（合理——由价格/波动驱动）；忽略了 (a) bump 后权益路径的二阶反馈，(b) available 不足导致的入场减少（回收 ×1.56 时非可忽略，见 §4.1），(c) 小钱包下 B 欠配对 pv 的反馈。10k 基钱包的分布混合了 2021-26 复合净值（后期 equity 数十倍放大），比例口径已消除该效应，但时代混合仍在。
- **时点性**：BTC 下限由 minQty×price 主导（80.6 @76.8k → 126 @120k），粒度误差随币价上行恶化；严肃门槛 3500 是"当前价"口径，对历史极价（121.8k）需 ~5500。
- **并发利用率**基于 A-only 回测的净值轨迹，AB 联合账户的净值路径不同（B 的盈亏会改变可用保证金时序），为近似。
- freqtrade 有效下限推导自 .venv 内 freqtrade 源码（`exchange.py:1096`、`wallets.py:414`），版本为当前 .venv 版本；升级 freqtrade 可能改变储备系数。
- 文档默认值（BTC ~100/步 0.001；ETH ~20/0.01；SOL ~5/0.1 或 1）未被使用——实时值已拿到；若未来复现时网络失败退回文档值，须按 §3 标注时点。
