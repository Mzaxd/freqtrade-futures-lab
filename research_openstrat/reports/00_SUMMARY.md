# 开源策略并行调研总结（2026-09-12）

4 个并行 agent 分头调研了 5 个开源仓库的策略，统一在 BTC/ETH/SOL（部分含 12 币扩展集）Binance 永续、fee 0.0005、freqtrade 2026.8 下回测。
协议：IS 2021-01-01→2022-12-31，VAL 2023 全年；**OOS 2024+ 未动用**。原始策略文件零改动，适配副本一律加前缀（F_/NC_/ND_）。

分报告：[agentA_nfi.md](agentA_nfi.md) · [agentB_official.md](agentB_official.md) · [agentC_community.md](agentC_community.md) · [agentD_freqai.md](agentD_freqai.md)

## 结论：值得拿出来优化的策略（按证据强度排序）

### 第一梯队（双窗口强证据，直接进优化管线）

| # | 策略 | 来源 | IS | VAL | 核心问题=优化杠杆 |
|---|---|---|---|---|---|
| 1 | NC_MomRegime15mFast | nateemma | +787.7%（市场+195%），DD 21.9% | +166.1%，DD 仅 9.6% | funding 净付 15.3k USDT 是最大出血点；3 币宇宙下部分参数不可辨识，扩宇宙后才值得调参 |
| 2 | VolatilitySystem | 官方库 | +8250%，PF 2.04，空头贡献 86% | +166.8%，PF 1.79 | SL=-1 无止损；IS 付 97k funding；ATR 乘数/重采样周期未调 |
| 3 | FSupertrendStrategy | 官方库 futures/ | +63.8%，1026 笔 | +49.0%，Sharpe 1.91，450 笔 | 全零衰减、样本最大；均利 0.18%/笔太薄 vs 双边费 0.1%；空头端完全空缺（2022 熊市没吃到） |

### 第二梯队（有真实 alpha 但需先动结构）

- **NFI X7**：信号库有真实 alpha（崩盘月盈利实证、IS/VAL 行为一致），但利润机制是 DCA/马丁（与实验室禁令冲突）、隐性浮亏最深 -59%~-72%、持仓 27-93 天。**只做信号提取，不整策略调参**：入场家族消融（82 家族中仅 ~10 个实际触发）、波动率/regime 门控、闪崩保护、funding 过滤、空头家族启用。
- **Supertrend**（官方库现货版）：VAL Sharpe 1.94/PF 1.31，但 IS DD 52.3%——先治回撤再谈优化；与 FSupertrendStrategy 同源，可做双策略投票融合。
- **NC_OversoldReversion**（nateemma）：IS +55.2%/PF 1.68，perp 上净收 funding 1686 U（占净利 34%）；2023 信号枯竭（1 笔）→ 放宽错位阈值重验 + 补对称做空端。
- **NC_KamaFama2**（Mastaaa1987）：96% 胜率模式可复现（IS +40.2%/150 笔），5 笔 -25% 硬止损吃掉 40% 净利 → 换时间/ATR 止损 + fastk 阈值 sweep。

### 观察线（低成本并行，不进主线）

- **FreqAI/LightGBM 管线**：基建已跑通（独立 venv `research_openstrat/.venv-freqai`，全年 3 对 15m 回测仅 10.6 分钟，无需 GPU）。官方模板基线 VAL -43%，但阈值 ±0.01→±0.02 一行改动减亏 29pp、回撤减半——信号有弱排序能力。方向：自有化模板（加 funding/regime 特征、阈值与再训练周期 sweep），QuickAdapterV3 只借鉴 extrema 标签思想。

### 明确淘汰

MultiMa（IS +75%→VAL -0.6%，过拟合实证）、FGodStra（0 trades，绝对价格阈值伪影）、FundingCarry（IS -7.1%）、KamaFama3（IS -29.1%，过度交易）。

## 跨策略共性发现

1. **funding 成本是全场最大可优化成本项**：VolatilitySystem（-97k）、MomRegime（-15k）、NFI 长持仓家族均被 funding 显著侵蚀；反过来 OversoldReversion 靠空头/持仓方向净收 funding。funding 符号/分位门控是横切所有候选的第一优先杠杆。
2. 2024+ OOS 窗口保持未污染，优化后按实验室协议走 walk-forward / stress 再放行。
3. 工程注记：freqtrade 2026.8 不递归扫描策略子目录（需 `--strategy-path user_data/strategies/oss`）、`--export-filename` 已移除（按内容重命名）；扩展数据集（9 币 × 2021-2023）已落库，LINK/DOT/LTC/UNI 的 funding 历史被 Binance 403 限流，按 0 费率回退。

## 阶段 1 结果（2026-09-12，详见 [phase1_optimization.md](phase1_optimization.md)）

第一梯队三策略的优化（IS 迭代 + VAL 单发，OOS 2024+ 零接触）。**无一全过门**，但收获结构性结论：

| 候选 | VAL 关键指标 | 过门 | 结论 |
|---|---|---|---|
| OPT1_VolatilitySystem（ATR 止损+1% 风险仓位+去 DCA，参数=原版信号值） | 102 笔 / +121.76% / DD 15.06% / Sharpe 0.93 / PF 2.20 | 4/5，差 Sharpe 0.07（CAGR 口径衰减仅 5.6%） | **回炉轻修**（阶段 2 首位：加追踪止损 + funding 门控）；funding -97k→-4.2k，DD 24.8→11.9，风险指标全面优于基线 |
| OPT1_FSupertrendStrategy（can_short+ROI 重调+funding 门控） | 751 笔 / -7.34% / DD 40.1% / PF 0.98 | 1/5 | **放弃该族调参线**（150 epochs 无一均利>0.3%，薄利结构性；空头 2021 净亏）；遗留假设：空头加 BTC regime 门 |
| OPT1_MomRegime15mLb21（funding 门控+lb 验证） | 53 笔 / +112.61% / DD 25.6% / Sharpe 0.52 / PF 2.52 | 2/5 | **回炉**（DD 治理 + funding 分位门）；**lb 可辨识性证实**：12 币下 lb21 比 lb14 利润 2.4 倍——宇宙扩容是参数辨识前提 |

公共产出：`opt_common.py` funding 门控（因果验证通过）。VAL 单发额度已各消耗 1 次；OOS 仍为净处女窗口。新增 5 个 OPT1_/opt_common 策略文件、9 个 opt1_* 结果 zip、4 份 phase1 报告。

## 阶段 2 结果（2026-09-12，详见 [phase2_optimization.md](phase2_optimization.md)）

两个方向被证伪（止步 IS、未耗 VAL），一个大幅改善但 VAL 仍未过门：

| 方向 | IS 结论 | VAL | 判定 |
|---|---|---|---|
| OPT2_VolatilitySystem（ATR 追踪+双边门控） | +55.16%/DD 21.4%/Sharpe 0.61，全面劣于 OPT1（消融证明劣化全来自追踪止损） | 未耗 | **证伪**：OPT1 维持冻结形态，追踪方向关闭 |
| OPT2_FSupertrendShortRegime（空头 BTC EMA200 门） | +59.93%<基线，DD 41.4%；1h EMA200 是 8 天快过滤器非牛熊 regime | 未耗（预注册门槛未过） | **证伪**：FSupertrend 调参线整体关闭 |
| OPT2_MomRegime15mLb21（DD 治理网格） | **REGIME_TOLERANCE=-0.03 决定性**：+590.93%/DD 36.03→16.81%/PF 2.18 | 59 笔/+115.56%/PF 2.56/DD 23.47%/Sharpe 0.55（2/5） | **大幅改善未过门**：离门槛差 DD 3.5pp、Sharpe 0.45 |

结构性发现：① risk-on 容差收紧是篮子策略的第一 DD 杠杆（利润不降反升）；② MAX_POSITION_WEIGHT 必须 > 1/TOP_N，否则剪枝/补仓永久空转（mpw30 病态配置导致 D2 agent 超时与回测不收敛的根因）。

当前全局最优形态不变：**OPT1_VolatilitySystem（VAL 4/5，差 Sharpe 0.07）> OPT2_MomRegime（2/5）**。VAL 单发累计消耗 4 次，OOS 2024+ 仍零接触。

## 阶段 3 结果（2026-09-12，详见 [phase3_final.md](phase3_final.md)）— 三阶段程序收官

- **MomRegime 家族关闭**：最后两种 sizing 杠杆交换比极差（93pp 利润换 1pp DD）或死杠杆（过渡带 DD 反升），冻结于阶段 2 终版（OPT2：+591%/DD 16.8%），不再投入。
- **OPT1_VolatilitySystem 终审记分卡 4/4 全过**（四半年度全正、三币全正、费率×3 后 +394.8%、lookahead 无偏）→ **建议消耗 OOS 单发**（2024-01→2026-09，冻结参数）。风险披露：入场延迟 1 根 1h K 线利润近乎减半（执行时点敏感）。
- 三阶段总账：VAL 消耗 4 发（P1×3/P2×1/P3×0），**OOS 0 发**；2 个优化方向与 1 个结构病态（mpw30）被干净证伪并记录。

## OOS 单发（程序终局，2026-09-12）

OPT1_VolatilitySystem @ 2024-01→2026-09（一切冻结，单次零重试）：**+69.11%（CAGR 21.5%）/ 301 笔多空双正 / Sharpe 0.35 / PF 1.24 / 0 爆仓 / funding 仅占利润 1.1%**，跑赢市场（+31.2%）与自研线（+19.8%/Sharpe 0.21）——预注册标准达成，**开源改造路线成立**。代价：**maxDD 37.14%**（2026-03→08，最近 6 个月，期末部分收复至距峰 -11%），远超 IS/VAL 的 12-15% 与自研线的 16% → **不建议直接 dry-run**。定位：方法论胜出、风险治理未达标。详见 [phase3_final.md](phase3_final.md) OOS 节。

最终账本：VAL 4 发，OOS 1 发（均已消耗）。

## 阶段 4 深度调优（2026-09-12，详见 [phase4_charter.md](phase4_charter.md) / [phase4_deepopt.md](phase4_deepopt.md)）— OPT4 冻结，dry-run 就绪

**终版 OPT4_VolatilitySystem**：OPT1 风险结构 + **atr08 波动门**（入场需 ATR≥0.8×30d 中位）+ 60d 时间止损 + 原厂信号参数 2.0/3h/2.0 + 12 币 MOT4。12 币优化池（2021-23）：**+1495.8% / DD 15.92% / Sharpe 1.01 / PF 1.97**，六半年窗全正（最差 +10.5%）。预注册 dry-run 门槛 6/6 硬门槛通过（fee×3 保留 81%、±0.1 高原成立、lookahead 无偏、**延迟 1 根保留 86%**）。污染窗回归（披露式）：+102.6%（12 币）/+89.6%（3 币），2026H1 型高波动震荡回撤 31-42% **未根治**（已知弱点，软门槛部分达成）。深调过程：参数面实为"利润/DD 拨盘"（原厂值胜出）；ADX/cooldown/MOT6/3x 追加证伪；DD 随 MOT 非单调取 4。启动包：`user_data/configs/config_opt4_dryrun.json` + 监控红线（30 天回撤 >20% 停机）。2024-26 窗口正式退役。

## 阶段 5 三门穷尽（2026-09-12，详见 [phase5_exhaustion.md](phase5_exhaustion.md)）

申报 11 变体 + 归因 + 组合数学全部测完（68 个 zip，未测清单为空），**历史数据可表达的优化空间宣告用尽**：

- **门 1（抗震荡门）全部证伪**：弱窗 DD 源于真突破后止损簇相关性，两个弱窗对门族响应互斥——入场侧过滤器结构性剪不掉。最近未过门者 ER1h-025（+1939.7%/DD 10.31，差 2 条门槛）记录为 live 研究臂、非采纳。
- **门 2（执行层）括号闭合**：被动限价存活率 94.6%、即时性溢价 8.9%——回测语义下限价几乎免费，决策移交 dry-run 双实例 A/B。
- **门 3 归因推翻假设**：OPT4 的钱 50.5% 来自 range、PF 最高在 trend_up（4.87），turbulent 不流血且与弱窗正交——三个 regime 叠加全拒；但**双 sleeve 组合过门**：corr 0.096、50/50 组合 Calmar 16.26 ≥ 门槛 13.5、DD 9.8%（36 个月口径，MomRegime 2023 段取自已耗 VAL zip 并披露）。
- 部署形态维持 OPT4 不变；剩余优化空间全部在回测之外（live A/B、ER 研究臂、双 sleeve 立项、未来 live 数据再优化周期）。

## 阶段 6 簇控/杂交/宇宙扩展（2026-09-12，详见 [phase6_final.md](phase6_final.md)）— 先优化后 dry-run 的收官轮

- **止损簇控制全族证伪**（重放置取证：簇入场净正期望 +30~60k，拒单=删赢家、权益垫变薄、DD 反而放大）；HYB_CC3 达成全部 DD 门槛（池 DD 8.73%）但利润只剩 42%，不过门。
- **宇宙迁移测试（本轮最重要）**：OPT4 在 11 个从未见过的新币上仅 **+36.71% / DD 42.59% / 3/6 子窗为负**（老池 +1495.8%/15.9）——老池数字是上界锚、新币是下界锚，真实预期偏下；**dry-run 白名单严禁扩展**。
- **MomRegime 24 币扩展证伪**（新币占 36% 笔数仅贡献 16% 利润）；sleeve B 维持 12 币冻结。
- **组合 v2（脚本修正后）更强**：corr 0.2275、50/50 组合 Calmar 19.66 ≥ 门槛 14.07——双 sleeve 是六阶段后唯一存活的改进。
- 六阶段优化空间审计终版：**全部穷尽**；历史数据再无未烧部分。交付 dry-run 包 v2（Sleeve A `config_opt4_dryrun.json` + 可选 Sleeve B `config_momreg_sleeve_dryrun.json`）。

## 阶段 7 遗珠计划（2026-09-12，详见 [phase7_salvage_final.md](phase7_salvage_final.md)）— 放宽协议 + 分家族 holdout

五条被毙/冻结线重启深研，**3 过 2 灭**：
- **NFI-Lite（真遗珠）**：DCA 依赖被家族消融破解，无 DCA 形态池内 +63.5%/**DD 4.0%**/PF 2.35、11 新币全正、corr(A)=-0.01——**危机收割凸性 sleeve**，三 sleeve 组合 A+B+NFI 40/40/20 把回撤 9.8%→6.9%、Calmar 16.3→18.2。
- **SuperDD（过门）**：Supertrend 风险治理版，DD 79→27.5%，新币 -24.6→+34.2%（风险结构版才迁移），holdout +18.8%。
- **Router 2.0（降级遗产）**：全路由不如静态 sleeve；**turbulent 暂停 overlay 是新币轴优于 OPT4 单体的资产**；v1"唯一 OOS 为正"系 3 币顺风窗局部现象。
- Reversion v2 灭（新币 -12.2%，funding 收入系单事件补贴）；FreqAI 灭（改善=少交易减亏，自有特征重要性 2.76%，费率墙）——S4 中途死亡由 S4b 续命收尾。

协议创新：2024-26 对非 VolSys 族首次作为一次性 holdout 使用（分家族烧毁账本）；11 新币对五族首次消耗。

---

## 产物索引

- 回测结果：`user_data/backtest_results/oss{A,B,C,D}_*.zip`（26 个）；`opt1_*_{is,val}.zip`（阶段 1，6+3 个）
- 指标汇总表：`user_data/reports/summary_oss*.{csv,md}`；`summary_opt1_all.{csv,md}`
- 新增策略：`user_data/strategies/oss/{NC_*,ND_*,FGodStra}.py`；`{opt_common,OPT1_*}.py`
- 仓库克隆：`research_openstrat/repos/`
