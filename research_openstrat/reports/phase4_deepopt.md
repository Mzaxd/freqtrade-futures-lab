# Phase 4 深度调优总报告 — OPT4_VolatilitySystem 冻结与 dry-run 判定（2026-09-12）

目标（负责人）：对 OPT1_VolatilitySystem 所有参数深度调优，使其完备、值得 dry-run。
章程：[phase4_charter.md](phase4_charter.md)（新数据协议 + 预注册门槛 + 参数盘点）。分工报告：[phase4_paramtune.md](phase4_paramtune.md)（G）· [phase4_structure.md](phase4_structure.md)（H）。

## 终版形态（frozen）

`user_data/strategies/oss/OPT4_VolatilitySystem.py` = OPT1 风险结构（ATR 锚定止损、1% 权益风险仓位、无 DCA、2x 杠杆、灾难 -0.30）+ **atr08 入场门**（重采样 ATR ≥ 0.8×30 天滚动中位才开新仓，多空同门，出场永不受门控）+ **60 天时间止损**（卫生项）+ 信号参数**保持原厂值 2.0/3h/2.0**。部署形态：12 币 × **MOT4**（`user_data/configs/config_opt4_dryrun.json`）。

## 冻结过程（三步仲裁，全部预注册规则裁定）

1. **参数面（G）**：4 个分层 hyperopt campaign（rs{2,3,4,6}，各 120 epochs，476/477 盈利）→ 预注册优胜 1.9/3.0；**关键披露：参数面本质是"利润/DD 拨盘"（宽止损经 1% 风险模型机械缩仓），原厂参数同窗利润仍占优**。
2. **结构面（H）**：atr08 门在 12 币上利润 +69%/DD -28%/弱窗 DD -31%（唯一有效门）；ADX 门、cooldown 证伪；MOT6、ts60 采纳，3x 杠杆拒绝。
3. **合并（C1/C2/C3 × MOT{3,4,5,6}）**：MOT6 交互损伤确认（6 槽并发使 2023-11 型止损簇叠加，DD 全部 >20%）；**C2_mot4 胜出**（DD≤20% 且利润≥+400% 中 Sharpe 最高、DD 最低）：12 币 **+1495.8% / DD 15.92% / Sharpe 1.01 / PF 1.97 / 433 笔 / 0 爆仓**。DD 随 MOT 非单调（16.2→15.9→27.3），MOT5 额外槽位恰接坏簇——选 MOT4 不选"更多分散更好"的直觉。

## 预注册 dry-run 门槛核验（7 项）

| # | 门槛 | 结果 | 判定 |
|---|---|---|---|
| 1 | 12 币与 3 币均正（2021-23） | +1495.8% / +977.9%（3 币 DD 11.95%、PF 2.42） | ✅ |
| 2 | 亏损半年窗 ≤1 且最差 >-10% | **6/6 全正**，最差 +10.5%（22H2） | ✅ |
| 3 | maxDD ≤20%（12 币）且 fee×3 为正 | 15.92%；fee×3 → +1216.4%（保留 81%） | ✅ |
| 4 | 参数高原（±0.1 邻域不塌陷） | 保留 69-110%（1.9/2.0、2.1/2.0、2.0/1.9、2.0/2.1 全正） | ✅ |
| 5 | lookahead 无偏 | no bias detected（2023 窗，20 信号） | ✅ |
| 6 | 延迟 1 根保留 ≥50% | **86.4%**（OPT1 仅 54%——门控剪掉了时序敏感的低波动边际入场） | ✅ |
| 7 | 软门槛：污染窗回归 DD 显著 <37.14% 且利润 ≥+30% | 利润 +102.6%（12 币）/+89.6%（3 币）✅；DD 42.3%（12 币）/31.2%（3 币）——3 币较 OPT1 的 37.1% 有改善但**未根治**，12 币更差 | ⚠️ 部分 |

**判定：6 项硬门槛全部通过 → 按预注册标准，OPT4 达到 dry-run 就绪。** 软门槛如实记录：2026-03→08 型"高波动无方向"震荡仍是已知弱点（atr08 门只滤低波动，滤不掉高波假突破），dry-run 期间应预期出现 30-40% 级回撤片段。

## 污染窗回归详情（披露式单次，运行后零迭代）

12 币 MOT4：+102.58%（CAGR 29.9%）/ DD 42.26%（2026-03-20→08-06）/ Sharpe 0.44 / PF 1.21 / 464 笔（260L/204S 双正）/ 0 爆仓 / funding 仅占利润 1.1%。
3 币：+89.60% / DD 31.19% / Sharpe 0.41 / PF 1.34。对照 OPT1 同窗 3 币（+69.11%/DD 37.14%/Sharpe 0.35）：利润 +20.5pp、DD -5.9pp、Sharpe +0.06——同向改善，幅度有限。回归后未做任何参数改动（协议要求）。

## Dry-run 启动包

- 配置：`user_data/configs/config_opt4_dryrun.json`（12 币、MOT4、futures/isolated、dry_run 钱包 10000、策略与 strategy_path 已内置）
- 命令：`.venv/bin/freqtrade trade --userdir user_data --config user_data/configs/config_opt4_dryrun.json`
- 监控要点（首 4 周）：① 胜率预期 25-35%，**连亏 10 笔属正常**（IS 最大连亏 10）；② 单笔风险恒 1% 权益，若单笔亏损 >1.5% 权益立即查滑点；③ atr08 门生效检验：低波动期应观察到入场频率骤降（对照 IS 中门挡掉 93 笔净亏交易）；④ kill-switch 红线：滚动 30 天回撤 >20%（IS 全窗从未超过）或任何爆仓 → 停机复盘；⑤ funding 月耗应 <利润 5%（IS/OOS 均 ~1%）。
- 升级路径：dry-run ≥8-12 周且行为与回测特征一致（入场率、持仓时长分布、门控触发率）→ 议小额实盘。

## 全参数处置总账（"所有参数"逐一交账）

| 参数 | 终值 | 依据 |
|---|---|---|
| signal_atr_mult | 2.0（原厂） | 合并比武胜出；拨盘留在工厂位，零过拟合自由度 |
| resample_hours | 3h（原厂） | 4 campaign 中 rs3 系最优 |
| stop_atr_mult | 2.0（原厂） | 同上（3.0 档 = 以利润换 DD 的备选，未采纳） |
| atr08 门 | 0.8×30d 中位 | H 线唯一有效结构，利润/DD/弱窗三赢 |
| time_stop | 60d | 卫生项（3 年仅 2 笔，防僵尸仓） |
| max_open_trades | 4 | DD 门槛约束下的最大分散度 |
| leverage | 2x | 3x 完全中性（保留爆仓缓冲） |
| risk_pct / margin_cap / stop floor | 1% / 35% / 0.5% | 实验室风险模型常量，冻结 |
| ADX 门 / cooldown / funding 门 / DCA / ROI / 追踪止损 | 无 | 分阶段证伪（阶段 2/4 记录在案） |
| 订单类型 | 全市价 | 保守口径（delay1 保留 86% 已证执行稳健） |

## 数据账本更新

本轮：2021-23 优化池内一切迭代；为回归单次下载了 9 币 2024-26 的 1h 数据（工具性，披露）；污染窗回归 2 次运行（12p/3p）后零迭代。VAL/OOS 正式额度零消耗。**2024-26 窗口自本轮起完全退役：任何后续优化不得再以它做任何形式的选拔或验收。**

## 产物清单（git 由负责人提交）

- 策略：`OPT4_VolatilitySystem.py`（终版）+ `OPT4_C{1,2,3}.py`、`OPT4_ParamTune*.py`×17、`OPT4_Struct_*.py`、`OPT4_sns*.py`×4（过程件）
- 配置：`user_data/configs/config_opt4_dryrun.json`
- 结果：`opt4_VolatilitySystem_{12p,3p}_is.zip`、`opt4_C*_{12p,12p_mot*}_is.zip`×9、`opt4_{s21h1..s23h2,fee3x,sns×4,delay×2,skip×2}`×12、`opt4_param_*`×17、`opt4_struct_*`×12、`opt4_VolatilitySystem_regress_{12p,3p}.zip`
- 报告：`phase4_{charter,paramtune,structure,deepopt}.md`；汇总 CSV `summary_opt4_*.{csv,md}`×5
- 日志：`user_data/logs/opt4_*.log`
