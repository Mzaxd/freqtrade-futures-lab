# 方案3 执行清单与配置草案 — ★ A_vt60f1 + B_2xvt 走完"解冻→影子前瞻→小仓部署"管道

> 性质:**调研 + 设计,不是实施**。本报告与 `drafts/` 下全部文件均为草案,未部署、未运行;
> 冻结文件(`deploy/*`、`user_data/strategies/oss/lvg_*.py` 等)零改动。
> 上游依据:`research_improve/MASTER_REPORT.md`(§1 推荐配置、§3 已知代价、§4 诚实性、§5 后续路径)、
> `research_improve/lvg/{pre_reg,report}.md`、`research_improve/port_pre_reg.md`、`research_ab/ws4_deployment.md`。
> 起草日期:2026-11-07。

## 0. 一段话裁决(管道就绪度)

**就绪度高、可直接进入 P0-P4**:两处改动的实现已作为独立策略类存在于
`user_data/strategies/oss/lvg_A_riskvol.py`(`LVG_A_vt60f1`,挂 OPT9 `_risk_fraction` 钩子,信号零改动)与
`user_data/strategies/oss/lvg_B_lev.py`(`LVG_B_2xvt`,`leverage()` 回调 clamp(2×60.6/RV30, 1, 2.5)),
回测产物 zip 齐全(port_a_vt60f1 = `backtest-result-2026-11-07_06-45-22.zip`、`lvg_full_b_2xvt.zip`),
部署侧有 ABN 栈 + ws4 蓝图的全部惯例可套。**最大缺口是 B 的 RV30 数据路径在 live/dry-run 下会静默冻结**
(`LVG_B_Lev._btc_daily_closes` 是一次性类级静态缓存,读 feather 后永不重读;每日刷新数据也进不了运行中的进程),
以及 A 的 `startup_candle_count=200`(1h)不足以让回收 SMA100 与 RV30 在进程启动时即生效(需 ~108 天历史)
——两者都必须以**新文件** `rev_B_2xvt` / `rev_A_vt60f1`(子类、信号逐字节不变)补齐后才能上影子栈。
建议影子期 **≥16 周、目标 24 周(6 个月)**,且至少覆盖一次 RV30 穿越目标带(60.6)引起的乘数带切换;
达标核心量化标准:工程一致性(vt/lev 状态行 vs 离线复算 ≥95% 逐日一致、B 0 强平、rev_ 类与 LVG_ 类同窗回测 trade-diff=0)、
轨迹偏差带(月收益差 |Δ|≤5pp、乘数分布占比差 ≤15pp)、风险画像(全程 dd30 ≥ -20%、从峰回撤 ≤ -35%、
月度收益落 MC P10-P90 带 ≥ 2/3)。样本量(3-6 个月)对"逐年跑赢"命题无检验力,只能证伪实现错误与画像外风险,
诚实披露见 §6。

---

## 1. 实现定位(已核实,含文件与行号)

### 1.1 A_vt60f1 = `LVG_A_vt60f1`

- **文件/类**:`user_data/strategies/oss/lvg_A_riskvol.py` L103-106。
- **继承链**:`LVG_A_vt60f1` → `LVG_A_VolTarget`(同文件 L39)→ `ARL_2x`(`AB_LevGrid.py` L24-26:
  `OPT9_Recycle` + `RECYCLE_MULT=1.21` + `leverage_fixed=2.0`)→ `OPT9_Recycle`(`OPT9_Recycle.py` L75)
  → `OPT9_VolatilitySystem` → `OPT8_VolatilitySystem` → `OPT4_VolatilitySystem` → `OPT1_VolatilitySystem`
  (1h, can_short, startup_candle_count=200)。
- **钩子**:override `OPT9_VolatilitySystem._risk_fraction`(钩子定义于 `OPT9_VolatilitySystem.py` L193-197,
  消费点在 `custom_stake_amount` L220 `risk = self.risk_pct * self._risk_fraction(...)`)。
  乘法发生在 `OPT9_Recycle.custom_stake_amount`(L180-199)施加 `RECYCLE_MULT` **之前** —— 回收层与 vt 层
  是相乘叠加,与回测语义一致。m_t = clamp(60.6/RV30, 1.0, 2.0)。
- **RV30 数据路径**:复用 `OPT9_Recycle._recycle_on` 惯例 —— `self.dp.get_pair_dataframe(BTC/USDT:USDT, 1h)`
  原始帧(`RECYCLE_REF` 已在 `informative_pairs` L85-92 声明,BTC 不在白名单也会被喂数),
  自切 strictly-before-current_time,重采样 1D 丢未完成日,warmup(<31 闭合日)→ m=1.0 中性。
  **live/dry-run 安全**(dp 实时蜡烛),tz/ms 归一化写法已含 d09ba64 教训(lvg_A_riskvol.py L58-63)。
- **依赖**:同目录 import(`AB_LevGrid` → `OPT9_Recycle` + `OPT2_MomRegime15mLb21`),`strategy_path:
  user_data/strategies/oss` 下可解析。

### 1.2 B_2xvt = `LVG_B_2xvt`

- **文件/类**:`user_data/strategies/oss/lvg_B_lev.py` L87-102。
- **继承链**:`LVG_B_2xvt` → `LVG_B_Lev`(L34)→ `OPT2_MomRegime15mLb21` → `OPT1_MomRegime15mLb21`
  → `OPT1_MomRegime15mFast`(15m, 纯多, TOP_N=3, regime=BTC 日线>SMA100×(1+tol) + 币自身 SMA50 + funding 门)。
- **钩子**:override `leverage()` 回调(L93-102):lev = clamp(2.0×60.6/RV30, 1.0, 2.5),再 min(max_leverage)。
  freqtrade 中杠杆是入场时属性,存量仓不改 —— 与回测一致(lvg report §七.6)。
- **RV30 数据路径(与 A 不同!)**:直接读磁盘 feather
  `user_data/data/binance/futures/BTC_USDT_USDT-1d-futures.feather`(L42-52),as-of 切片严格因果。
- **依赖**:同目录 import;B 全家(regime 面板 `_daily_closes`、funding 门 `opt_common`)均读磁盘 feather;
  `opt_common` 的 funding 缓存是 **mtime 感知**的(commit 7ea932c,长跑进程免重启读新数据),
  `OPT1._daily_closes` 每次调用重读文件 —— 这两层都能吃到 scheduler 每日刷新。

### 1.3 排除项

- `uni_ARLGate.py`:UNI 线的 A 袖点时宇宙门控,MASTER §2 已裁"不进组合",与本管道无关,不引入。
- `bull_*.py`(V1f/V1f2x):BULL 线产物,★ 未采用(解冻面更大的备选),不引入。

### 1.4 能否被 dry-run 配置直接引用?

| | 直引 `LVG_A_vt60f1` | 直引 `LVG_B_2xvt` |
|---|---|---|
| import 可解析 | 可以(同目录链完整) | 可以 |
| 信号语义 | 与回测一致 | 与回测一致 |
| live 数据路径 | dp 实时,BTC 1h 有喂 | **静态缓存:进程启动时读一次 feather 后永不重读**(L40-52) |
| warmup | **startup_candle_count=200(1h)≈8.3 天**:回收 SMA100 需 ≥100 闭合日、RV30 需 ≥31 闭合日 → 影子栈启动后前 ~100 天回收层静默 OFF + m=1(双重中性,偏离 ★ 回测语义) | 无 warmup 问题(读全历史 feather) |
| 可观测性 | 无 vt 状态日志(乘数不可监控) | 无 lev/rv30 状态日志 |

**结论:都不能裸上。** 按 lab 纪律(冻结文件不许编辑、新东西=新文件、`oss/<前缀>_*.py`),
最小改动 = 两个新子类文件(草案见 `drafts/rev_A_vt60f1.py`、`drafts/rev_B_2xvt.py`,执行时复制到
`user_data/strategies/oss/`),信号零改动:

1. `rev_A_vt60f1.py`:`Rev_A_vt60f1(LVG_A_vt60f1)` —— ① `startup_candle_count = 2600`(108 天 1h,
   Binance 单次 1500 根×5 批内,使回收 SMA100 与 RV30 从第一根起可算);② 每小时一条可 grep 的
   `REV-VT status rv30=.. m=..` 日志行(乘数分布 gate 的数据源)。
2. `rev_B_2xvt.py`:`Rev_B_2xvt(LVG_B_2xvt)` —— ① `_btc_daily_closes` 改 mtime 感知缓存(opt_common 惯例,
   scheduler 00:10Z 刷新 feather 后免重启生效),含 >36h 陈旧告警;② 入场时 `REV-LEV status` 日志行。
3. 回归验证(预注册):rev_ 类 vs LVG_ 类同窗(`20210101-`)回测 **trade-diff = 0**(startup 只影响 live 预热,
   日志无副作用;若非 0,书面解释后才放行)。预算 2 次回测。

### 1.5 回测产物与数据(复跑/合成用,均已存在)

- A_vt60f1 全窗口:`user_data/backtest_results/backtest-result-2026-11-07_06-45-22.zip`(PORT 补测,
  3 币 BTC/ETH/SOL、MOT 4、wallet 7000、2021-01-01→2026-11-07)。
- B_2xvt 全窗口:`user_data/backtest_results/lvg_full_b_2xvt.zip`(3 币、MOT 3、wallet 3000)。
- 冻结基线:`backtest-result-2026-11-07_03-54-11.zip`(A)/`03-56-10.zip`(B)。
- 关键数字(MASTER §1/§3 + lvg results.json):★ 组合 23/24/25/26 = +176.7/+137.5/+37.4/+7.6,
  dd30 全窗 -14.6%,21-26 +7324%;A_vt60f1 袖 +4672%/maxDD 43.5%;B_2xvt 袖 21-26 +21760.8%/0 强平;
  2026 已知代价:年内从峰 -31~-33.6%、-5/-6 月 -11.7/-12.8%。
- 注意:★ 的回测口径是 **3 币宇宙 + 7000/3000 钱包**(70/30 语义 = 钱包比例),
  而当前 NAS ABN 栈 sleeve config 是 12 币白名单、A=OPT4(非 ARL_2x)—— **NAS 栈既不是冻结 AB 研究口径,
  也不是 ★ 口径**,影子栈必须独立新建(§3),且影子对照基准 = 同窗离线重放,不是 NAS 栈曲线。

---

## 2. 执行清单(总览;逐项勾选版见 checklist.md)

管道沿用 lab 既定路径与 ws4 蓝图惯例(G0-G6 门禁结构),阶段映射:

```
P0 解冻决议+重预注册 → P1 可部署子类+回归验证(G0') → P2 MC 自助(WS2式) → P3 红线复核(G4')
→ P4 影子栈上线验收(G1') → P5 影子期运行与达标裁决(G2'/G3') → P6 小仓实盘(G5')
```

| 阶段 | 动作 | 新文件 | 验收标准 | 预计耗时 |
|---|---|---|---|---|
| P0 | 所有者书面解冻决议:★ 为唯一候选;写 `pre_reg_shadow.md`(候选、影子 gates、kill 规则、MC 参数、禁调参条款),先于任何新观察 | `research_revive/pipe/pre_reg_shadow.md` | 决议落档、预注册含 §3/§5 全部阈值 | 0.5 天 |
| P1 | rev_A/rev_B 子类落地 + 同窗回归 | `oss/rev_A_vt60f1.py`、`oss/rev_B_2xvt.py`(源:drafts/) | trade-diff=0×2;REV-VT/REV-LEV 日志行出现;`python -c "import"` 无错 | 1 天(含 2 次回测) |
| P2 | MC 块自助:袖曲线从两个 zip 提取(CONTEXT §6 法)→ 联合块自助 → dd30 分位/P(触-20%)/180d 窗口分布/月度 P10-P90 带 | `research_revive/pipe/mc_ws2_shadow.py`(源:drafts/)、`results_mc.json` | 与 ws2_analysis.py 惯例一致(块 30d、2000 路、固定 seed);输出四组统计齐全 | 0.5 天 |
| P3 | 红线复核:MC p95 vs -20%;影子期判定带(P10-P90)冻结进预注册附录;若 p95 破线 → 收紧或否决 | `pre_reg_shadow.md` 附录修订 | 阈值书面冻结;MC p95 未破 -20%(破线则按预注册处置) | 0.5 天 |
| P4 | 影子栈上线:compose + 2 config + 凭据 patch + 监控;与冻结 ABN 栈并行、互不干扰 | `deploy_shadow/{docker-compose.shadow.yml, config_shadow_a_vt60f1.json, config_shadow_b_2xvt.json, monitor_shadow.py}`(源:drafts/) | ws4 §2.2 式 10 项验收全绿(版本/白名单 3 币/dry_run/钱包 7000+3000/策略加载/REST/调度继承/REV 状态行/监控首跑) | 1 天 |
| P5 | 影子期:日检(scheduler.log+状态行复算)→ 周报(权益/偏差带)→ 月评审(§5 监控表) | `deploy_shadow/monitor/*`(运行产物) | §3.3 gates 全部满足(≥16 周)或按 kill 规则处置 | 12-24 周(日检 ≤5 分钟) |
| P6 | 达标后小仓实盘:子账户×2(ws4 §4.1)、API 权限最小化、qty/min-notional 校验、资金 ≤ 总额 25%、首周逐笔对账 ≥95% 一致 | `deploy_live/`(届时新建) | ws4 §4 全关闭;G5' 清单 | 达标后 1-2 天准备 |

回测预算申报:P1 用 2 次(diff 验证);P5 期间每月可用 1 次"同窗重放"作轨迹对照(数据刷新后 feather 即真样本外,
重放不引入新信息,只测执行差异)。

---

## 3. 影子前瞻配置草案

### 3.1 改哪三个 sleeve config?

**一个都不改。** 冻结的 `deploy/config_sleeve_{a,b,c}.json` 与 `docker-compose.abn.yml` 原样保留(NAS 冻结栈继续跑,
作为"部署纪律仍在运转"的对照,但注意 §1.5:它不是 ★ 的对照基准)。影子栈全部新文件,放 `deploy_shadow/`:

| 冻结文件 | 影子对应物(新) | 关键差异 |
|---|---|---|
| `config_sleeve_a.json`(OPT4,12 币,4500) | `config_shadow_a_vt60f1.json` | strategy→`Rev_A_vt60f1`;白名单 12→**3 币**(回测口径);wallet 4500→**7000**;db→`tradesv3_shadow_a.dryrun.sqlite`;端口 8084;补 NAS 代理三件套(e90b518) |
| `config_sleeve_b.json`(OPT2,12 币,2500) | `config_shadow_b_2xvt.json` | strategy→`Rev_B_2xvt`;白名单→3 币;wallet→**3000**;db→`tradesv3_shadow_b.dryrun.sqlite`;端口 8085;代理三件套 |
| `config_sleeve_c.json`(NFI-Lite,不参与 ★) | 不建(★ 只有 A/B 两袖) | — |
| `docker-compose.abn.yml` | `docker-compose.shadow.yml` | 两策略容器;不建 scheduler(数据刷新**复用**冻结栈 scheduler:00:10Z 12 币 1h/15m/5m/1d+funding 已覆盖影子栈所需 3 币全部口径);新增影子监控容器(日频) |

草案全文见 `drafts/`(JSON/YAML/py 头部均标注"草案,未部署")。凭据生成沿用 DEPLOY_UNRAID §2 patch 脚本模式。

### 3.2 策略类换成什么

- A 袖:`Rev_A_vt60f1`(= `LVG_A_vt60f1` + startup 2600 + 状态日志;信号逐字节不变)
- B 袖:`Rev_B_2xvt`(= `LVG_B_2xvt` + mtime 感知 RV30 缓存 + 陈旧告警 + 状态日志;信号逐字节不变)

### 3.3 影子期长度与达标标准(量化,写入预注册)

**长度:最低 16 周,目标 24 周(6 个月),且至少覆盖一个"乘数带切换事件"**(RV30 穿越 60.6 使 A 的 m 或
B 的 lev 离开当前界;若 24 周内无事件,按 ws4 §2.3 边界情形出具中期报告,由所有者书面决定,不得改带定义)。

达标 gates(全部满足才谈资金):

1. **工程一致性(前 4 周必须全绿)**
   - REV-VT / REV-LEV 状态行 vs 本地 feather 离线复算 RV30:逐日一致 ≥95%(允许日界/tz 边界差);
   - 零 ImportError、零 funding 告警持续 >24h、B 袖 0 强平(回测口径 0/134);
   - rev_ vs LVG_ 同窗回放 trade-diff=0(P1 已验,不重复);
   - B 的 BTC 1d feather mtime 每日更新(复用冻结栈 scheduler,监控容器检查)。
2. **轨迹偏差带(≥8 周后按月评估)**
   - 影子组合月收益 vs 同窗 freqtrade 回测重放月收益:|Δ| ≤ 5pp/月(滑点/定价/order book 的执行差异带);
   - 乘数分布:m(t) 与 lev(t) 落在 [界值] 的时间占比,影子 vs 回测同期差 ≤15pp;
   - 影子日收益与重放日收益相关系数 ≥0.7。
3. **风险画像(全程)**
   - 组合 dd30 全程 ≥ -20%(红线,触发走 §5 处置,不是"不达标"而是"停机");
   - 组合从峰回撤 ≤ -35%(回测画像最深 -33.6% + 1.4pp 余量;破线=画像外,停机复盘);
   - 单月 ≤ -13%(回测最差月 -12.8% + 余量)累计出现 ≥2 次 → 人工复核;
   - P2 熔断事件(同向止损簇拒单)≤2 次/月。
4. **样本与分布**
   - ≥90 个日频点 + ≥3 个完整月度点;
   - 月度收益落 MC P10-P90 带(P2/P3 产出)≥ 2/3;
   - 影子期组合不要求绝对为正(2026 型环境本就薄),但**不得同时**满足"dd30 触 -18% + 两个 ≤-10% 月"
     (该形态 = 回测 2026 出血段的放大版,触发即复核)。

不达标处置:延长影子期 1 倍重评;连续两轮不达标 → 候选降级回"假设生成",冻结 AB 部署不动。

---

## 4. MC 自助(WS2 式)复用方式

**既有惯例(已核实)**:

- `research_ab/ws2_analysis.py`:对 (rA, rB, s) 同日三元组**联合块自助**,块长 30d、2000 次、seed=20261103;
  每路径算 30d 滚动 DD 最深 → p5 分位与 P(触 -20%)。数据源 = `user_data/logs/mtm_daily_{A3,B3}.csv`。
- `research_deepen/portfolio/scripts/prt08_wboot.py`:平稳自助(Politis-Romano,均值块长 10d)10000 路 seed=42,
  权重格点 argmax 稳定性 + Calmar/maxDD 分位 CI —— 用作敏感性对照。
- `research_deepen/inference/scripts/inf_bootstrap.py`:stationary + iid(块长 1)对照 + trade-level shuffle
  —— 序列依赖贡献的分解惯例。
- 袖曲线提取标准法(CONTEXT §6):zip 内 `<strategy>_wallet.feather`(列 date/total_quote)→
  `resample('h').last().ffill()` → 两袖相加;末端用结果 JSON `profit_total_abs` 锚定(已知坑:末根强平/未平仓
  不计入 feather 末端)。

**本管道复用**(草案脚本 `drafts/mc_ws2_shadow.py`,执行时复制到 `research_revive/pipe/` 运行):

1. 输入:`backtest-result-2026-11-07_06-45-22.zip`(A_vt60f1 钱包曲线)+ `lvg_full_b_2xvt.zip`(B_2xvt);
   各自锚定终值后逐小时合成组合权益 → 日收益 (rA, rB) 联合序列(保留袖间同日相关)。
2. 主口径:块自助 块 30d、2000 路、固定 seed(建议 20261107);每路径同时重放 A、B 两条权益再相加
   (保住 70/30 复合路径依赖,不是对组合日收益直接重采样)。
3. 输出四组统计(红线复核 P3 与影子判定带 P5 的输入):
   - 全窗 dd30 最深分布:p5/p50/p95、P(dd30 ≤ -20%);
   - **180d(影子期)窗口**:窗口末组合收益分布(P(末值<0)、P10/P50/P90)、窗口内 dd30 最深 p95;
   - 月度收益 P10-P90 带(逐月,影子期月评审对照);
   - iid(块长 1)对照:量化块结构对尾部 DD 的贡献(ws2/inf 惯例)。
4. 敏感性:均值块长 10d 平稳自助(prt08 惯例)重跑一遍;两口径结论方向不一致时以更保守者入预注册。

---

## 5. 监控与 kill 规则草案(对应 ★ 已知代价)

监控载体:新 `deploy_shadow/monitor_shadow.py`(草案在 drafts/,改自 `deploy/monitor_portfolio.py`:
2 bots、独立 CSV `deploy_shadow/monitor/equity_shadow.csv`,避免污染冻结栈的 equity_daily.csv),
日频随冻结栈 scheduler 之后跑;同时输出袖级 dd30、月度收益行、REV 状态行复算结果。

| # | 已知代价/风险(来源) | 监控点(日频) | REVIEW(人工看) | STOP(停机复盘) |
|---|---|---|---|---|
| K1 | 2026 年内从峰 -31~-33.6%(MASTER §3.1) | 组合从峰回撤 | ≤ -28%(画像带内逼近) | **≤ -35%(画像外)** |
| K2 | 月度序列 -5/-6 月 -11.7/-12.8%(§3.2) | 月度收益行 | 单月 ≤ -13%,或连续两月 ≤ -10% | 三月连负且累计 ≤ -20% |
| K3 | A_vt60f1 袖级 maxDD 43.5% vs 冻结 34.9%(§3.3) | A 袖 dd30 + 从峰 | 袖 dd30 ≤ -20% | 袖 dd30 ≤ -25%(停 A 容器,B 继续) |
| K4 | 组合 dd30 红线(章程) | 组合 dd30 | ≤ -18%(红线前 2pp 预警) | **≤ -20%(章程红线,两容器全停)** |
| K5 | B 强平回测 0 笔(lvg §六) | REST trades 强平计数 | — | **≥1 笔即停 B**(结构假设破坏) |
| K6 | B RV30 数据陈旧(本报告 §1.4 发现) | BTC 1d feather mtime、REV-LEV 状态行 | 陈旧 >36h(告警行) | 陈旧 >48h(停 B,恢复后免重启) |
| K7 | A vt 数据退化(dp 路径) | REV-VT 状态行 m 回 1.0 且 rv30=NA 天数 | NA 连续 ≥3 日 | NA 连续 ≥7 日(停 A) |
| K8 | P2 熔断聚集(opt9_forensic §4) | 同向止损簇计数(监控容器统计) | ≥3 次/月 | ≥6 次/月 |
| K9 | 权重漂移(70/30) | a/(a+b) 占比 | 偏离 ±10pp | —(季度再平衡,ws4 §5.2) |
| K10 | 影子 vs 重放偏差带 | 月度 |Δ|、乘数占比差 | 超 5pp / 15pp(单月) | 连续两月超带(停,复盘执行差异) |

停机后流程沿用 ws4 §2.4 预注册协议:复盘四问书面存档 → 影子模式继续记曲线(不作 gate)→ 影子权益创 30d 新高
方可重启;观察期内禁改策略(基础设施问题只修 deploy_shadow/ 层)。

---

## 6. 风险与诚实性披露

1. **选择效应打折**:★ 的"4/4 全过"建立在 ≈17+ 次对 24-26 的观察之上(LVG 单发+BULL 单发+UNI 两 arm+
   PORT 12 格矩阵+补测);且 A_vt60f1 的入选本身受 r2 2026 失败的事后启示(装配期数据知情选择),
   B_2xvt 出自 7 格 IS 网格。按保守读法:即使每次观察独立、单次通过率 50%,4/4 全过的联合概率也仅 ~6%
   量级 —— **回测优势应按大幅折价对待(经验上 ≥减半),任何披露必须携带本条**。影子前瞻正是为选择效应买单的
   唯一干净检验。
2. **影子期检验力诚实**:16-24 周 ≈ 90-168 个日频点 / 4-6 个月度点。对"逐年跑赢基准"这种年度命题
   **无检验力**(月度收益噪声 σ≈8-13%,检验两均值差需要数十个月);影子期能检验的只有三件事:
   实现正确性(工程 gate)、行为与回测一致性(偏差带)、风险未出画像(K1-K10)。它不能证明 edge 存在,
   只能否决最坏情形 —— 报告与所有者沟通必须用这个措辞。
3. **已知代价不可消除**:年内深回撤(-31~-33.6%)、连续失血月、A 袖 maxDD 43.5% 是 ★ 的结构性代价
   (放大器的另一面),监控只做"画像外检测",不存在"既保 +176/+137 又不付 2026 型代价"的免费选项
   (CRASH 线三次证伪)。
4. **口径差**:回测(dry-run wallet、fee 0.0005、feather 成交)≠ 影子(order book 定价、滑点、资金费);
   资金费在 B 2-2.5x 杠杆下的拖累回测已近似计入,但影子期必须实际观测(偏差带 5pp 的主要成分预期来自此)。
   回测全窗 +7324% 是复合路径依赖产物,不可外推。
5. **本报告自身**:全部实现定位基于对现行代码的逐行阅读(版本 = 当前 HEAD eb1d7b2),rev_/monitor/MC 脚本
   为**未运行草案**;startup_candle_count=2600 对回测的等价性(trade-diff=0)是推断,必须由 P1 验证;
   freqtrade 2026.8 live 蜡烛缓存行为(初始抓取 = startup_candle_count)按官方语义陈述,P4 验收第 8 项复核。
