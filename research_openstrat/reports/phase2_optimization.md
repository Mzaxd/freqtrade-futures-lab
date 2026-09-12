# Phase 2 优化总报告（阶段 2/3）— 2026-09-12

协议同阶段 1：迭代仅 IS 20210101-20230101；VAL 单发仅用于晋级候选（本阶段仅 MomRegime 终版消耗 1 次）；**OOS 2024+ 零接触**；未修改任何已存在文件（阶段 2 新建文件除外）。

分报告：[phase2_volatilitysystem.md](phase2_volatilitysystem.md) · [phase2_fsupertrend.md](phase2_fsupertrend.md) · MomRegime 网格见本文（D2 agent 超时，网格由主会话接手完成）。

## 结果一览

### B2：OPT2_VolatilitySystem（ATR 追踪止损 + 双边 funding 门控）— 方向证伪，不晋级，未耗 VAL

| | OPT1（阶段 1 冻结） | OPT2（追踪+门控） |
|---|---|---|
| IS profit / DD | +424.22% / 11.92% | +55.16% / 21.42% |
| IS Sharpe / PF | 0.99 / 2.37 | 0.61 / 1.35 |

归因诊断（gate-only 与 trail-only 消融）：劣化几乎全部来自追踪止损——该系统利润结构依赖"让趋势跑到反转信号"，3h ATR 尺度的中段锁盈直接破坏它；funding 门控在选中阈值 0.0013 下对 IS 零拦截（敞口缩小 84% 纯属仓位变小）。150 epochs 内 trail 维单调指向"追踪越少越好"。半年度子窗也不均衡（21h1 +1.9% / 21h2 +28.7% / 22h1 +23.5% / 22h2 −2.2%）。**结论：OPT1 维持阶段 1 冻结形态，追踪方向关闭。**

### C2：OPT2_FSupertrendShortRegime（空头 BTC regime 门）— 假设证伪，未耗 VAL

BTC 1h EMA200 门把 2021 空头亏损从 -6128 减半到 -3216 但没剪干净（2021 年有 46.2% 的小时 BTC 在 1h EMA200 下方——它是约 8 天的快趋势过滤器，不是牛熊 regime）；2022 空头红利完整保留（+4138）。总 IS +59.93% < 基线 +63.75%，DD 41.44% ≫ 24%——预注册 VAL 门槛双双未过。SMA200 变体更差。**FSupertrend 系最终结论：IS 最优形态就是原版全多基线，该族调参线关闭。**

### D2：OPT2_MomRegime15mLb21（DD 治理网格）— IS 大幅改善，VAL 仍未过门

网格（2×2×2=8 格 + 1 格结构性作废，12 币，IS）：

| 配置 | trades | profit% | maxDD% | Sharpe | PF | funding |
|---|---|---|---|---|---|---|
| mpw45_tol0_abs（=阶段1优胜，复现 ✓） | 60 | +542.50 | 36.03 | 0.29 | 1.84 | -11,828 |
| mpw45_tol0_q80 | 61 | +504.57 | 35.01 | 0.30 | 1.84 | -11,421 |
| **mpw45_tolm3_abs（优胜）** | **52** | **+590.93** | **16.81** | **0.31** | **2.18** | -11,307 |
| mpw45_tolm3_q80 | 53 | +540.37 | 16.89 | 0.32 | 2.16 | -10,998 |
| mpw35_tol0_abs | 60 | +478.53 | 34.72 | 0.29 | 1.82 | -10,336 |
| mpw35_tol0_q80 | 61 | +428.41 | 33.51 | 0.30 | 1.81 | -9,811 |
| mpw35_tolm3_abs | 52 | +452.74 | 23.06 | 0.30 | 2.05 | -9,535 |
| mpw35_tolm3_q80 | 53 | +400.77 | 20.94 | 0.30 | 2.01 | -9,128 |

- **REGIME_TOLERANCE=-0.03 是决定性杠杆**：risk-on 要求 BTC ≥ SMA100 上方 3%，砍掉 2022 边缘 regime 翻转的反复进出，DD 36.03→16.81 的同时利润反升到 +590.93%。
- mpw35（仓位上限）只贡献 1-2pp DD 改善且吃利润；q80 门控近似中性（省 funding 3% 但利润 -9%）。
- **结构性发现（作废记录）**：mpw30 为病态配置——仓位上限 0.30 < 等权目标 1/TOP_N=0.333，触发"剪枝→补仓"永久空转，回测 15 分钟不收敛（D2 agent 超时与两次卡死的根因）。任何 MAX_POSITION_WEIGHT 设置必须 > 1/TOP_N。

**VAL 单发（12 币，2023）**：59 笔 ✓ / +115.56% / **PF 2.56 ✓** / maxDD 23.47% ✗（>20%）/ Sharpe 0.55 ✗ / 衰减：原始口径 80% ✗、CAGR 口径 29% ✓。较阶段 1 的 VAL 全面改善（DD 25.57→23.47、笔数 53→59、PF 2.52→2.56）但仍未过门。

## 阶段 2 总结论

1. **两个优化方向被干净证伪**（VolSys 追踪止损、FSup 空头 regime 门）——都止步于 IS，未浪费 VAL 额度。
2. **MomRegime 是最大赢家**：IS DD 减半（36→16.8）利润反升（542→591），VAL 三项指标继续改善但 Sharpe/DD 仍未过门。它离过门只差"VAL 期 DD 23.5%→<20% 和 Sharpe 0.55→1.0"。
3. 当前全程最优形态仍与阶段 1 一致：**OPT1_VolatilitySystem（VAL 4/5）> OPT2_MomRegime（2/5）**。

## 阶段 3 建议（最终选拔）

- 淘汰名单确定：FSupertrend 族、VolSys 追踪方向、MomRegime mpw30 结构。
- MomRegime 最后一轮 DD 杠杆（在 2021-2023 内）：per-coin 波动率目标仓位 或 2022 型 bear-regime 内强制半仓；若仍不过门则接受 OPT1_VolatilitySystem 为阶段 3 唯一晋级者。
- 阶段 3 对晋级者做：2021-2023 内 rolling walk-forward（不触 OOS）+ 费率/滑点/延迟压力测试 + lookahead-analysis，产出"是否值得消耗 OOS 单发"的最终建议。

## 过程异常与披露

1. D2 agent 10 分钟无输出超时死亡两次链路中断：其根因是 mpw30 病态配置使回测不收敛（非 agent 逻辑错误；其代码与 8 个变体文件经审查质量合格，q80 门控双重因果保护）。网格由主会话接手跑完。
2. 主会话一次 shell 事故：zsh 下 `set -- $tag` 不分词，曾生成 4 个文件名带空格的非法变体并把 D2 遗留旧 zip 误重命名为 mpw35 结果——已全部删除并以显式文件重写、验证 import 后重跑（带失败保护的落盘脚本）。受影响仅为 mpw35 四格，mpw45 四格与最终结论使用的是干净重跑结果。
3. `opt2_{is,val}_SupertrendMa.zip`（08:55-08:56）为用户上次中断会话的遗留产物，早于本会话阶段 1（09:00 起），未触碰。
4. VAL 单发账本：阶段 1 用 3 次（VolSys/FSup/MomRegime），阶段 2 用 1 次（MomRegime 终版）。OOS 仍零接触。

## 新增文件清单（git 由实验室负责人提交）

- 策略：`user_data/strategies/oss/OPT2_VolatilitySystem.py`、`OPT2_FSupertrendShortRegime.py`、`OPT2_MomRegime15mLb21.py` + 8 个网格子类 `OPT2_MomRegime15mLb21_<tag>.py`
- 结果：`opt2_VolatilitySystem_is.zip` + 4 个半年度子窗 zip、`opt2_FSupertrendShortRegime_is.zip`、`opt2_MomRegime_<8 tags>_is.zip`、`opt2_MomRegime15mLb21_{is,val}.zip`（+meta）
- 报告：`research_openstrat/reports/phase2_{optimization,volatilitysystem,fsupertrend}.md`
- 汇总：`user_data/reports/summary_opt2_mom_grid.{csv,md}`、`summary_opt2_finals.{csv,md}`；日志 `user_data/logs/opt2_*.log`
