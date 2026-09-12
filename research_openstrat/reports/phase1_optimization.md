# Phase 1 优化总报告（阶段 1/3）— 2026-09-12

协议执行情况：全部迭代/hyperopt 仅用 IS 20210101-20230101；每个最终候选 VAL 20230101-20240101 恰好回测一次（共 3 次，已消耗）；**OOS 2024+ 保持零接触**（日志审计 `grep -E "Backtested 202[3-6]-" user_data/logs/opt1_*.log` 为空）。未修改任何已存在文件；新增文件见文末清单。基线引用 ossB_/ossC_ 已有结果，未重跑。

分报告：[phase1_volatilitysystem.md](phase1_volatilitysystem.md) · [phase1_fsupertrend.md](phase1_fsupertrend.md) · [phase1_momregime.md](phase1_momregime.md)
统一指标：`user_data/reports/summary_opt1_all.{csv,md}`（summarize_results.py 口径，与基线报告一致）。

## 工作项 A：公共 funding 门控（opt_common.py）

- 因果性：8h 结算事件序列 shift 1 期后 `merge_asof` 对齐 K 线（K 线只能看到上一次已结算费率），单元测试验证通过；缺数据币（LINK/DOT/LTC/UNI，Binance 403）NaN 放行并告警披露。
- `funding_gate_long/short(df, threshold)`，阈值参数留在各策略 hyperopt 空间（上界≈哨兵值可自学关闭）。

## 过门判定（门槛：trades≥50 / PF≥1.3 / Sharpe≥1.0 / maxDD≤20% / VAL 衰减<50%）

| 策略 | 窗口 | trades | profit% | CAGR% | maxDD% | Sharpe | PF | funding | 判定 |
|---|---|---|---|---|---|---|---|---|---|
| OPT1_VolatilitySystem | IS | 139 | +424.22 | 128.96 | 11.92 | 0.99 | 2.37 | -4,190 | |
| （基线 IS：+8,250.79 / DD 24.77 / Sharpe 0.60 / PF 2.04 / funding -97,432） | **VAL** | **102 ✓** | **+121.76** | 121.76 | **15.06 ✓** | **0.93 ✗** | **2.20 ✓** | -439 | **未过（差 0.07）** |
| OPT1_FSupertrendStrategy | IS | 1709 | +23.03 | 10.92 | 34.37 | 0.27 | 1.02 | -1,537 | |
| （基线 IS：+63.75 / Sharpe 0.86 / 单笔均利 0.18%） | **VAL** | 751 ✓ | -7.34 ✗ | -7.34 | 40.14 ✗ | -0.30 ✗ | 0.98 ✗ | -19 | **未过（1/5）** |
| OPT1_MomRegime15mLb21 | IS | 60 | +542.50 | 153.48 | 36.03 | 0.29 | 1.84 | -11,828 | |
| （12 币基线 IS：+189.33 / DD 28.49 / PF 1.41 / funding -8,059） | **VAL** | 53 ✓ | +112.61 | 112.61 | 25.57 ✗ | 0.52 ✗ | 2.52 ✓ | -707 | **未过（2/5）** |

衰减口径说明：IS=2 年、VAL=1 年。原始读数下三者衰减 71%/负增长/79% 均不过；CAGR 年化读数下 VolatilitySystem 衰减仅 5.6%、MomRegime 26.6%。本报告以**严格原始读数为主判定**（未过门），CAGR 读数作为参考——两种口径下结论不变：无策略全过门。

## 各策略结论与下一步

### OPT1_VolatilitySystem — 最接近过门，建议回炉轻修（阶段 2 首位）
- 修改：ATR 止损（锚定入场 ATR，stop=2.0）+ 1% 风险仓位 + 去 DCA；参数冻结为原版信号参数（2.0×ATR/3h），hyperopt 67 epochs 最优反而不及其一（采样未覆盖，详见分报告）。
- 成效：funding -97k→-4.2k（-96%）；DD 24.8→11.9/15.1；PF、Sharpe 双窗口全面优于基线；0 强平。VAL 仅 Sharpe 0.93（差 0.07）与衰减口径两项不达标。
- 阶段 2 建议：加 ATR 追踪（当前仅初始止损）或分档 trailing 提平滑度；funding 门控接入（本项未含）；修完直接复检 VAL 不再可用（已单发），改走 walk-forward 内验证。

### OPT1_FSupertrendStrategy — 优化方向被证伪，建议放弃该族调参线
- 修改：can_short=True（激活现成空头端）+ funding 门控（收敛到 0.0011≈关闭）+ ROI 表 hyperopt（150 epochs **0 个 epoch 单笔均利 >0.3%**，空间上限 0.116%——薄利是结构性的）。
- IS 全面劣于基线（+23.0% vs +63.8%，Sharpe 0.27 vs 0.86）；空头端 2022 熊市 +4040 但 2021 牛市 -6128，净 -2106；VAL -7.34%（基线 VAL +49%/Sharpe 1.91）。基线自身也过不了门（PF 1.20<1.3、DD 24.4%>20%）。
- 遗留假设（若阶段 2 想救）：空头加 BTC regime 门（仅 SMA200 下方允许开空）后重验 IS。

### OPT1_MomRegime15mLb21 — 结构性收获大，指标未过门，建议回炉
- 修改：funding 门控（入场+加仓两处，funding_max=0.0005 固定工程阈值）+ lb 参数 12 币宇宙验证。
- **lb 可辨识性证实**：3 币下 Lb21≡Fast（逐字节同），12 币下 73→60 笔、+227%→+542%、PF 1.49→1.84——宇宙扩容是参数辨识的前提，这是本轮最重要的结构性结论。
- 门控效果：绝对 funding 未省（-8,059→-8,231，权益更大所致），强度下降（funding/净利 42.6%→36.3%），同 lb 下利润 +189%→+227%；未触发关闭条件，保留。
- 未过门主因：VAL Sharpe 0.52、DD 25.6%（IS DD 36% 同样超标）。阶段 2 建议：DD 治理（MAX_POSITION_WEIGHT 0.45 下调 / regime 容差收紧 / 波动率门）+ funding 分位门（当前绝对阈值）。

## 过程异常与披露
1. Agent-B（VolatilitySystem）10 分钟无输出超时死亡；hyperopt 67/150 epochs 处 loky worker 崩溃（结果文件完整）。主会话接手完成裁定与 VAL。
2. FSupertrend hyperopt 的 loky worker 无法 import 同目录 opt_common，agent 以 sys.path 注入 + PYTHONPATH 解决；其自动导出 sidecar 已删除保持 .py 权威（VolatilitySystem 的 e10 sidecar 同样处理）。
3. LINK/DOT/LTC/UNI 无 funding 历史（Binance 403）：门控放行、回测不计其 funding，MomRegime 三跑同等低估。
4. FSupertrend hyperopt 产物 236MB fthypt 留存于 user_data/hyperopt_results/（可删）。

## 新增文件清单（git 由实验室负责人提交）
- 策略：`user_data/strategies/oss/opt_common.py`、`OPT1_VolatilitySystem.py`、`OPT1_FSupertrendStrategy.py`、`OPT1_MomRegime15mFast.py`、`OPT1_MomRegime15mLb21.py`
- 结果：`user_data/backtest_results/opt1_{VolatilitySystem,FSupertrendStrategy,MomRegime15mLb21}_{is,val}.zip`、`opt1_MomRegime12pBase_is.zip`、`opt1_MomRegime15mFast_is.zip`（+对应 .meta.json）
- 报告：`research_openstrat/reports/phase1_{optimization,volatilitysystem,fsupertrend,momregime}.md`
- 汇总：`user_data/reports/summary_opt1_all.{csv,md}`；日志：`user_data/logs/opt1_*.log`
