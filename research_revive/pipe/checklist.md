# 方案3 执行清单(可勾选)— ★ A_vt60f1 + B_2xvt 解冻→影子前瞻→小仓部署

> 纪律:冻结文件(`deploy/*`、`user_data/strategies/oss/*.py` 既有文件、冻结 config)一律不改;
> 一切新东西 = 新文件;每步先看验收标准,全绿才勾。依据:report.md(同目录)+ ws4_deployment.md 惯例。
> 起草 2026-11-07,当前状态:全部未开始。

## P0 解冻决议 + 重预注册(0.5 天)

- [ ] P0.1 所有者书面解冻决议:★ A_vt60f1 + B_2xvt 为**唯一**候选;冻结 AB 部署栈(NAS ABN)原样保留
  - 动作:决议一句话 + 日期 + 签名,写入 `research_revive/pipe/pre_reg_shadow.md` 头部
  - 验收:决议落档;明确"不改任何冻结文件"
- [ ] P0.2 起草 `research_revive/pipe/pre_reg_shadow.md`(先于任何新观察):
  候选定义(两策略类 + 3 币 + 7000/3000)、影子 gates(report §3.3 四组)、kill 规则(report §5 表)、
  MC 参数(块 30d/2000 路/seed)、每月 1 次同窗重放配额、禁调参条款、B_v1f2x 等备选**不**进入本管道
  - 验收:预注册包含全部量化阈值;commit 后才允许进 P1 之后任何回测
- [ ] P0.3 回测预算申报:P1 计 2 次(rev_ 回归),P5 期间每月 ≤1 次(同窗重放,执行差异对照)
  - 验收:预算表进预注册

## P1 可部署子类 + 回归验证(1 天;预算 2 次回测)

- [ ] P1.1 复制 `drafts/rev_A_vt60f1.py` → `user_data/strategies/oss/rev_A_vt60f1.py`
  - 内容:`Rev_A_vt60f1(LVG_A_vt60f1)`;startup_candle_count 200→2600;每小时 `REV-VT status rv30= m=` 日志行
  - 验收:`.venv/bin/freqtrade list-strategies` 含 Rev_A_vt60f1(或 python import 无错)
- [ ] P1.2 复制 `drafts/rev_B_2xvt.py` → `user_data/strategies/oss/rev_B_2xvt.py`
  - 内容:`Rev_B_2xvt(LVG_B_2xvt)`;`_btc_daily_closes` mtime 感知缓存(>36h 陈旧告警);入场 `REV-LEV status` 日志行
  - 验收:同上;确认未触碰 `lvg_B_lev.py`(git status 干净)
- [ ] P1.3 回归验证 A:`Rev_A_vt60f1` 20210101- 同参数(3 币、MOT4、7000)vs `LVG_A_vt60f1` 冻结 zip
  (06-45-22):trades 明细 diff = 0
  - 命令模板:`scripts/run_backtest.sh Rev_A_vt60f1 20210101- p1_rev_a -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT --max-open-trades 4 --dry-run-wallet 7000`
  - 验收:diff=0;非 0 → 书面解释(允许:startup 预热差导致的指标位差)后才放行
- [ ] P1.4 回归验证 B:`Rev_B_2xvt` 同窗(3 币、MOT3、3000)vs `lvg_full_b_2xvt.zip`:diff = 0
  - 验收:同上
- [ ] P1.5 日志行冒烟:本地 `freqtrade backtesting ... --timerange 20260901-20261107` 各 1 次短窗,
  确认 REV-VT/REV-LEV 状态行输出且数值与手工复算一致(注:短窗仅为日志冒烟,不新增观察口径)
  - 验收:grep 到状态行;RV30 与本地 feather 复算一致(±0.1)

## P2 MC 自助 — WS2 式(0.5 天)

- [ ] P2.1 复制 `drafts/mc_ws2_shadow.py` → `research_revive/pipe/mc_ws2_shadow.py`
  - 惯例来源:`research_ab/ws2_analysis.py`(联合块自助、块 30d、2000 路、固定 seed)+
    `research_deepen/inference/scripts/inf_bootstrap.py`(iid 对照)+ CONTEXT §6 袖曲线提取法
- [ ] P2.2 运行并产出 `research_revive/pipe/results_mc.json`:
  (a) 全窗 dd30 p5/p50/p95 + P(≤-20%);(b) 180d 窗口末收益分布 + 窗口 dd30 p95;
  (c) 月度收益 P10-P90 带;(d) iid 对照
  - 验收:四组齐全;seed 固定可复现;两端点用 profit_total_abs 锚定(CONTEXT §6 已知坑)
- [ ] P2.3 敏感性:均值块长 10d 平稳自助(prt08_wboot.py 惯例)重跑;与主口径方向不一致 → 以保守者入预注册
  - 验收:敏感性结果写入 results_mc.json 附注

## P3 红线复核 — G4'(0.5 天)

- [ ] P3.1 判定:MC 全窗 dd30 p95 是否 ≥ -20%?
  - 是 → 继续;否 → 预注册处置(影子红线收紧至 MC p95 或否决候选,书面)
- [ ] P3.2 冻结影子期判定带(月度 P10-P90、180d 窗口分布)进 `pre_reg_shadow.md` 附录
  - 验收:附录 commit;此后不许再改带
- [ ] P3.3 kill 阈值定稿(report §5 表 K1-K10 写入预注册;K4 组合红线保持章程 -20%)
  - 验收:预注册含全部触发条件与处置动作

## P4 影子栈上线 — G1'(1 天)

- [ ] P4.1 复制 drafts → `deploy_shadow/`:`docker-compose.shadow.yml`、`config_shadow_a_vt60f1.json`、
  `config_shadow_b_2xvt.json`、`monitor_shadow.py`;`chmod +x`
  - 验收:deploy/ 目录 git status 零改动
- [ ] P4.2 凭据 patch(DEPLOY_UNRAID §2 模式,对 config_shadow_*.json)+ `deploy_shadow/.monitor_env`(600)
- [ ] P4.3 NAS 上 `docker compose -f deploy_shadow/docker-compose.shadow.yml up -d`
  (与冻结 ABN 栈**并行**;容器名/端口 8084/8085 不冲突;db 文件全新)
- [ ] P4.4 验收清单(ws4 §2.2 式,10 项全绿):
  - [ ] 1. 两容器 Up;freqtrade 2026.8(docker logs | grep -i version)
  - [ ] 2. 白名单 = 且仅 BTC/ETH/SOL(两实例日志)
  - [ ] 3. dry_run 标记、exchange key 为空;初始钱包 A=7000 / B=3000
  - [ ] 4. 策略加载 `Rev_A_vt60f1` / `Rev_B_2xvt` 无 ImportError
  - [ ] 5. REST ping 通(8084/8085)
  - [ ] 6. 数据新鲜:BTC/ETH/SOL 1h/15m/1d+funding feather mtime = 当日(冻结栈 scheduler 00:10Z 覆盖)
  - [ ] 7. 首条 `REV-VT status` / `REV-LEV status` 日志行出现且与离线复算一致
        (startup 2600 生效验证:rev-A 首行 rv30 非 NA、m 非 1.0-暖机值)
  - [ ] 8. 监控首跑:`deploy_shadow/monitor/equity_shadow.csv` 首行;dd30/ddPeak 输出 OK
  - [ ] 9. 代理三件套连通(容器内 curl -x … api.binance.com ping;e90b518 教训)
  - [ ] 10. 冻结栈 8081-8083 三容器不受影响(ps 对比)
- [ ] P4.5 影子期 T0 时刻与初始权益快照写入 `pre_reg_shadow.md`(前向窗口起点,唯一干净数据)

## P5 影子期运行与达标裁决 — G2'/G3'(12-24 周)

**日常(≤5 分钟/天)**
- [ ] D.x 看 `deploy_shadow/monitor/` 日志:OK/REVIEW/RED;状态行 vs 复算;
  feather mtime;强平计数=0;K1-K10 无触发
  - 纪律:REVIEW → 当日人工看;RED/STOP → 按 report §5 停机协议 + 复盘四问存档 `research_revive/pipe/postmortems/`

**周(30 分钟)**
- [ ] W.x 权益/袖级 dd30/从峰回撤快照入周报;权重占比 a/(a+b);REV 状态行周汇总(m/lev 分布)

**月(1 小时)**
- [ ] M.x 同窗重放(预算内 1 次):刷新 feather 后回测同月窗口 → 月收益差 |Δ|、日收益相关、乘数占比差 → 对照 §3.3 gates
- [ ] M.y 月度收益落 MC P10-P90 带判定;月度评审表追加(逐月 4-6 个点)
- [ ] M.z 乘数带切换事件计数(≥1 为 G3' 主判据)

**达标裁决(≥16 周后任意月评审时点)**
- [ ] G-a 工程 gate:状态行一致 ≥95% / 0 强平 / 数据陈旧事件 = 0
- [ ] G-b 轨迹 gate:全部已评估月份 |Δ|≤5pp、乘数占比差 ≤15pp、相关 ≥0.7
- [ ] G-c 风险 gate:全程 dd30 ≥-20%、从峰 ≤-35%、K2/K8 未达 STOP
- [ ] G-d 样本 gate:≥90 日频点、≥3 月度点、落带 ≥2/3、含 ≥1 乘数带切换事件
- [ ] G-e 全绿 → 出具影子期终版报告 + 所有者裁决是否进 P6;任一不绿 → 延长 1 倍或降级(报告 §3.3)

## P6 小仓实盘 — G5'(达标后 1-2 天准备,另行预注册细则)

- [ ] P6.1 Binance 子账户 ×2(强制,ws4 §4.1:双实例共享账户会互相污染 sizing)
- [ ] P6.2 API key 权限最小化(仅 Enable Futures、禁提现、IP 白名单书面取舍)
- [ ] P6.3 qty/min-notional 校验:load_markets 导出限额 → 对照影子期 stake 分位数(≥1.2× 余量)
- [ ] P6.4 资金 ≤ 目标总额 25%;70/30 划入两子账户
- [ ] P6.5 首周逐笔对账:实盘成交 vs 同期影子/重放信号一致性 ≥95%;拒单 0 或逐笔可解释
- [ ] P6.6 台阶加仓规则(+25%/≥4 周台阶,ws4 G6)书面化

## 附:禁止事项(全程有效)

- 禁止编辑:deploy/ 任何文件、user_data/strategies/oss/ 既有策略、user_data/configs/*
- 禁止:影子期内改策略参数/带定义/kill 阈值(基础设施 bug 只修 deploy_shadow/ 层;策略级 bug = 停机走复盘)
- 禁止:重开 CRASH 方向、参数调优、恒定放大(MASTER §5.3);B_v1f2x 不许"顺手"比较
- 禁止:在影子期结束前用任何真实资金
