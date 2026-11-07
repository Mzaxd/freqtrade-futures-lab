# research_lowvol 前向影子预注册(2026-11-08 起生效,先于任何前向观察写定)

> 依据:MASTER_REPORT §5。本文件写定后,前向期内的任何调参/换配/重跑都不被承认;
> 违反即宣告影子失效。冻结 AB 部署栈(NAS)不动,影子栈独立新建。

## 1. 注册候选(两个,并行影子,不许中途增删)

- **P1(主)cell49**:A_vt60f1 30% + B_2xvt 30% + SlowA_12h_r3 40%(3 币 BTC/ETH/SOL,月度再平衡)
- **P2(副)cell40**:B(OPT2 冻结)30% + SlowA_12h_r3 70%(月度再平衡)

资金划分以影子钱包初始值固定;月度再平衡=每月首个交易日手动调 dry-run 各袖 available_capital
(记录表:`shadow_rebalance_log.csv`,日期/各袖权益/目标权重/偏差)。

## 2. 影子栈工程前置(全部新文件,参考 research_revive/pipe/checklist.md)

- [ ] `rev_A_vt60f1.py`:`LVG_A_vt60f1` 子类;startup_candle_count 200→2600;每小时 `REV-VT status rv30= m=` 日志
- [ ] `rev_B_2xvt.py`:`LVG_B_2xvt` 子类;BTC 日线 feather mtime 感知缓存(>36h 告警);`REV-LEV status` 日志
- [ ] `rev_SlowA_r3.py`:`SlowA_12h_r3` 子类;同样审查 12h 周期下的 startup_candle 与缓存语义(回收 SMA100 日线 + ATR 暖机),日志 `REV-SLOWA status`
- [ ] 三份 dry-run 配置(3 币、独立 shadow 目录,复用 deploy 口径但独立实例)
- [ ] 回归验证:三个 rev_ 类对同窗回测 trade-diff=0(vs 各自母类 zip:09-30-08 / lvg 系列 / 03-56-10)

## 3. 影子 gates(≥16 周起评,目标 24 周;至少覆盖一次 RV30 穿 60.6 换挡)

| # | Gate | 阈值 |
|---|---|---|
| G1 | 实现一致性:rev_ 状态行 vs 离线复算 | ≥95% 一致 |
| G2 | B_vt / B 强平 | 0 |
| G3 | 同窗重放偏差(月收益 vs 回测重放) | \|Δ\| ≤ 5pp |
| G4 | vt/lev/slowa 乘数分布 vs 回测分布 | 占比差 ≤ 15pp |
| G5 | 组合 dd30(装配口径) | ≥ -30%(红线,破即人工停机复核) |
| G6 | 组合从峰回撤 | ≥ -35%(画像外,停机) |
| G7 | 月收益落 MC 自助带(P10-P90) | ≥ 2/3 月份在内 |

诚实条款:3-6 个月样本对"低波年更优"无检验力,只能证伪实现错误与画像外风险;
达标结论 = "可谈资金与解冻",不是"优势确认"。回测优势按 MASTER_REPORT §4 折价披露。

## 4. 观察预算

影子期内同窗回测重放 ≤ 每月 1 次(执行差异对照用),不许任何参数/权重/尺度变更;
P1/P2 中途都不许换权重。24 周期满出 `shadow_report.md`,由户主决定是否进入资金阶段。

## 5. 多重检验账本衔接

本预注册不消耗新回测预算;全部选择已在 MASTER_REPORT §4 入账
(research_improve 17+ → slowa 4 尺度 → LV1 4 变体 → LV2 50 格 → wave2 20 格)。
