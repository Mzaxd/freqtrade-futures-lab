# WS4 — AB + 动态调仓 + 3 币 部署蓝图（ws4_deployment.md）

> 性质：**设计/综合文档**，不含新回测。所有数字均引自既有材料（CONTEXT.md、24-26 诊断、
> opt9_forensic_program.md、4+1 个 live-fix commit）。未完成工作流的依赖以「[待 WSx 结论]」占位。
> 蓝图口径：dry-run 先行（本部署栈延续"永远 dry-run 直到 G5"纪律），实盘迁移作为独立阶段（§4）。

## 0. 摘要（结论先行）

- **架构**：把现有 ABN 三 sleeve 栈（`deploy/docker-compose.abn.yml`）收缩为**两 sleeve + scheduler**：
  A = `OPT9_Recycle`（WS3 交付，继承 OPT9 修复链，MOT 4）占 64% 预算，B = `OPT2_MomRegime15mLb21`
  （MOT 3 = TOP_N）占 36%，3 币 BTC/ETH/SOL。C（NFI-Lite）下线。
- **预算语义**：freqtrade 无"百分比预算"配置；64/36 通过**每实例独立 dry_run_wallet**（名义总额
  10000 → A=6400 / B=3600）实现，A 的 1% 权益风险 sizing 与 B 的 pv/TOP_N 等权 sizing 均以自身
  钱包为权益基数，故"64% 语义 = 钱包设为总资金 64%"。漂移由季度再平衡管理（§5.2），**不做日度
  再平衡**——与 WS2 回收模拟（日度再平衡口径）的该差异已列入披露（§9）。
- **MOT 3 vs 4 口径差（已核对）**：B 的 12 币诊断跑在 `OPT7_config_12p.json`（MOT 4）上，而
  deploy config 是 MOT 3。代码证据表明行为等价（§1.3），建议部署用 MOT 3 并在启动前做一次
  零成本 diff 核验。
- **dry-run 观察 gate**：验收 10 项全绿 → 常规 8 周 → **至少 1 个完整 BTC 破线周期**（乘子
  on→off 完整翻转对 + ≥3 笔放大交易）→ WS2 MC/红线复核 → 小资金实盘（≥[待 WS1 结论]）→
  分台阶加仓。
- **已知 live bug 对策**：4 个 live-fix commit（微秒时间戳 6065744 / 定价+代理 c389a98 / tz·单位
  d09ba64 / NAS 代理 e90b518）+ funding cache 修复（7ea932c）+ OPT8 42d 潜伏 bug（8d30ab8，
  OPT9 已修）全部映射为部署验收项或日检项（§4.5）。

---

## 1. 目标架构与差异清单

### 1.1 容器拓扑（4 → 3 容器）

| 容器 | 角色 | 变化 |
|---|---|---|
| ft-ab-a | A 实例 `OPT9_Recycle`，127.0.0.1:8081 | 策略换名（OPT4_VolatilitySystem → OPT9_Recycle）、config/db 换新文件 |
| ft-ab-b | B 实例 `OPT2_MomRegime15mLb21`，127.0.0.1:8082 | config/db 换新文件，策略名不变 |
| ~~ft-ab-c~~ | ~~NFI-Lite~~ | **删除**（8083 释放） |
| ft-ab-scheduler | 每日 00:10Z 刷新 + 00:40Z 监控 | 保留；内部命令改 3 币 + 2 bots（§2.1.3） |

### 1.2 与 `deploy/docker-compose.abn.yml` 的差异（新文件 `deploy/docker-compose.ab.yml`）

按硬性规则本工作流不改已跟踪文件，以下为新文件内容（落地动作见 §8）：

```yaml
services:
  sleeve-a-opt9:
    image: freqtradeorg/freqtrade:2026.8
    container_name: ft-ab-a
    volumes:
      - ./:/freqtrade
    command: >
      trade --config deploy/config_ab_a.json
      --strategy OPT9_Recycle
      --db-url sqlite:////freqtrade/user_data/tradesv3_ab_a.dryrun.sqlite
    ports:
      - "127.0.0.1:8081:8080"
    restart: unless-stopped

  sleeve-b-momregime:
    image: freqtradeorg/freqtrade:2026.8
    container_name: ft-ab-b
    volumes:
      - ./:/freqtrade
    command: >
      trade --config deploy/config_ab_b.json
      --strategy OPT2_MomRegime15mLb21
      --db-url sqlite:////freqtrade/user_data/tradesv3_ab_b.dryrun.sqlite
    ports:
      - "127.0.0.1:8082:8080"
    restart: unless-stopped

  ab-scheduler:
    image: freqtradeorg/freqtrade:2026.8
    container_name: ft-ab-scheduler
    volumes:
      - ./:/freqtrade
    entrypoint: ["/bin/sh", "/freqtrade/deploy/scheduler_loop_ab.sh"]
    restart: unless-stopped
```

差异逐条：

| # | 项 | 旧（abn） | 新（ab） | 理由 |
|---|---|---|---|---|
| 1 | sleeve-c 服务 | 存在 | **删除** | C 下线（frozen 决策：AB 两 sleeve） |
| 2 | A strategy | OPT4_VolatilitySystem | **OPT9_Recycle** | OPT9 取证修复（be_floor/P2 熔断/时间止损豁免 + 42d bug 修复）+ 回收层 [待 WS3 结论：类名与继承确认] |
| 3 | A config/db | config_sleeve_a.json / tradesv3_abn_a.dryrun.sqlite | **config_ab_a.json / tradesv3_ab_a.dryrun.sqlite** | db 换名：避免与旧 ABN 栈的 A 残留持仓/权益混淆；旧 sqlite 归档不删 |
| 4 | B config/db | config_sleeve_b.json / ..._abn_b... | **config_ab_b.json / tradesv3_ab_b.dryrun.sqlite** | 同上 |
| 5 | scheduler entrypoint | scheduler_loop.sh | **scheduler_loop_ab.sh**（新文件，§2.1.3） | 刷新命令换 3 币 config + timeframe 集合；monitor 换 2 bots |
| 6 | 镜像/端口/restart | 2026.8 / 127.0.0.1:808x / unless-stopped | 不变 | OPT9 的 set_custom_data 在 2026.8 已验证（run-3 dry-run 先例） |

**与旧栈互斥**：ft-ab-* 容器名与 8081/8082 端口和旧 ABN 栈冲突，上线前先
`docker compose -f deploy/docker-compose.abn.yml down`（旧 equity_daily.csv 归档见 §3.1）。

### 1.3 A 的 budget/stake：从 4500 到 64% 语义

- 现状：`config_sleeve_a.json` 的 `dry_run_wallet: 4500`（= 三 sleeve 时代 45%：4500/2500/3000，
  总 10000）。
- 新语义：**每实例钱包 = 总资金 × 权重**。名义总额 10000 USDT →
  - A：`"dry_run_wallet": 6400`
  - B：`"dry_run_wallet": 3600`
- 机理：A（OPT4/OPT9 系）sizing 为 `notional = equity × risk_pct / stop_pct`、`stake = notional/2x`、
  上限 `equity × margin_cap(0.35)/笔`，equity 即本实例钱包；B sizing 为 `target = pv / TOP_N`
  （pv = 本实例 MTM 权益）。两策略都以自身钱包为 100%，所以**权重即钱包比例**，freqtrade 层
  无需也无法表达"百分比"。
- 实际总资金 ≠ 10000 时按比例缩放，但受 [待 WS1 结论：最小运行资金门槛] 下限约束（门槛未达
  则不启动实盘阶段；dry-run 可先用名义 10000）。
- A 的 `max_open_trades` 保持 **4**（OPT4 冻结口径；3 币宇宙下最多 3 仓并发，MOT 4 不改变行为，
  与回测 config 一致）；`stake_amount: "unlimited"`、`tradable_balance_ratio: 0.99` 不变。

### 1.4 B 的 MOT 3 vs 诊断 MOT 4 —— 核对结论与建议

**事实**：B 的 12 币 24-26 诊断（`DP_SleeveB`，report_2426_diagnostic.md）用
`OPT7_config_12p.json` → `max_open_trades: 4`；deploy config（config_sleeve_b.json）是 MOT 3。

**代码核对**（`user_data/strategies/oss/OPT1_MomRegime15mFast.py`，OPT2 继承不改）：

1. 入场信号 `enter_long` 仅在 `hold=True`，而 `hold` 由 `_hysteresis_membership` 的
   **TOP_N=3 槽位扫描**产生——第 4 槽永远不会有信号，MOT 4 的额外槽位不会被用到；
2. `custom_stake_amount` 里 `stake = min(proposed_stake, target, fillable, max_stake)`，
   `target = pv/3` 恒 ≤ MOT=4 下的 `proposed_stake`（unlimited 时 = free/(MOT-open)）——
   proposed 从不构成绑定约束；
3. 类注释明写 `TOP_N = 3  # == config max_open_trades`——MOT 3 才是策略作者声明的配置不变量。

**结论**：两者预期产生**逐笔相同**的交易序列，差异属于口径噪音而非行为差异。
**建议**：部署 config 用 **MOT 3**（与策略不变量一致），并在启动前做零成本核验——同一窗口
（如 20240101-20260912，12 币）DP_SleeveB 各跑 MOT 3 / MOT 4，`trades` 明细 diff = 0。此为
配置卫生核验而非调参，不触碰预注册纪律；若 diff ≠ 0（预期不会），差异写书面分析后再定。

### 1.5 回收乘子的部署暴露 [待 WS3 结论]

- 候选值：半回收 1.28 / 全回收 1.56，触发条件 = BTC 日收盘 < SMA100（与 B 牛熊开关联动），
  **取值由 WS2 预注册定夺**，部署 config/策略属性以 WS3 交付为准。
- 触发数据源：BTC 1d feather（B 的 REGIME_REF 同源）→ 每日 00:10Z 数据刷新后生效，
  与 scheduler 节奏天然对齐。
- 监控暴露方式（乘子当前值/翻转时间/累计放大交易数）见 §3.3；**部署验收依赖 WS3 提供至少
  一条可 grep 的乘子状态日志行**（§2.2 第 8 项）。

---

## 2. dry-run 阶段计划

### 2.1 配置文件具体改动

#### 2.1.1 `deploy/config_ab_a.json`（新文件）

```json
{
  "$schema": "https://schema.freqtrade.io/schema.json",
  "bot_name": "ab-sleeve-a-opt9recycle",
  "dry_run": true,
  "dry_run_wallet": 6400,
  "cancel_open_orders_on_exit": false,
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "max_open_trades": 4,
  "stake_currency": "USDT",
  "stake_amount": "unlimited",
  "tradable_balance_ratio": 0.99,
  "fiat_display_currency": "USD",
  "dataformat_ohlcv": "feather",
  "initial_state": "running",
  "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"},
  "entry_pricing": {"price_side": "other", "use_order_book": true, "order_book_top": 1,
                    "price_last_balance": 0.0,
                    "check_depth_of_market": {"enabled": false, "bids_to_ask_delta": 1}},
  "exit_pricing": {"price_side": "other", "use_order_book": true, "order_book_top": 1},
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "ccxt_config": {
      "httpsProxy": "http://192.168.73.103:7897",
      "wsProxy": "http://192.168.73.103:7897",
      "wssProxy": "http://192.168.73.103:7897"
    },
    "ccxt_async_config": {},
    "pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
    "pair_blacklist": []
  },
  "pairlists": [{"method": "StaticPairList"}],
  "internals": {"process_throttle_secs": 5},
  "strategy": "OPT9_Recycle",
  "strategy_path": "user_data/strategies/oss",
  "api_server": {"enabled": true, "listen_ip_address": "0.0.0.0", "listen_port": 8080,
                 "username": "CHANGEME_USER", "password": "CHANGEME_PASSWORD",
                 "jwt_secret_key": "CHANGEME_RANDOM_SECRET", "CORS_origins": [],
                 "verbosity": "error"}
}
```

相对 `config_sleeve_a.json` 的字段变化：`bot_name`、`dry_run_wallet` 4500→**6400**、
`pair_whitelist` 12→**3** 币、`strategy` 换名、`ccxt_config` 加**LAN 代理三件套**
（`192.168.73.103:7897` 为当前 NAS 环境 mihomo 实例，若 IP 变更按 §5.4 runbook 更新；
`use_order_book: true` 两侧保持——c389a98 教训，见 §4.5）。凭据生成沿用 DEPLOY_UNRAID.md §2
的 patch 脚本（对 `config_ab_*.json` glob）。

#### 2.1.2 `deploy/config_ab_b.json`（新文件）

与 A 的差异字段（其余同上，含代理三件套）：

```json
{
  "bot_name": "ab-sleeve-b-momregime",
  "dry_run_wallet": 3600,
  "max_open_trades": 3,
  "strategy": "OPT2_MomRegime15mLb21"
}
```

相对 `config_sleeve_b.json`：`dry_run_wallet` 2500→**3600**（25%→36%）、`pair_whitelist`
12→**3**、MOT 保持 **3**（§1.4）。

#### 2.1.3 `deploy/scheduler_loop_ab.sh`（新文件 = scheduler_loop.sh 的两处改动）

1. `run_refresh` 的 download-data 命令：

```sh
freqtrade download-data --userdir user_data \
    --config user_data/configs/OPT7_config_3p.json \
    --timerange 20210101- --timeframes 1h 15m 1d \
    --logfile user_data/logs/refresh_daily.log
```

   - config 从 `OPT7_config_12p.json` → **`OPT7_config_3p.json`**（已存在的 3 币回测 config，
     复用其 pair_whitelist，不改已跟踪文件；download-data 只读 pair 列表）。
   - timeframes 去掉 **5m**（唯一消费者 NFI-Lite 已下线；A 用 1h（3h 信号为 1h 内部重采样），
     B 用 15m + 1d + funding）。futures 模式下 funding_rate feather（`-1h-funding_rate.feather`）
     随 download-data 自动更新。
2. `run_monitor` 的 bots 列表：

```sh
python deploy/monitor_portfolio.py --once \
    --bots http://sleeve-a-opt9:8080,http://sleeve-b-momregime:8080 \
    >> deploy/monitor/cron.log 2>&1
```

   （compose 内网服务名随 §1.2 改为 `sleeve-a-opt9`；需与 monitor_portfolio.py 的两 sleeve
   适配（§3.1）同步落地。）其余（00:10Z/00:40Z、catch-up、日志格式）不变。

### 2.2 验收清单（dry-run 启动 gate，逐条全绿）

1. 旧栈已 down；`docker compose -f deploy/docker-compose.ab.yml ps` 三容器 Up。
2. 版本：两实例 `docker logs ft-ab-a 2>&1 | grep -i version` → freqtrade **2026.8**。
3. 白名单：两实例日志各含且仅含 BTC/ETH/SOL 三个 USDT-M 永续。
4. dry-run：`dry_run` 标记、exchange key 为空；初始钱包 **A=6400 / B=3600**。
5. 策略加载：`OPT9_Recycle` / `OPT2_MomRegime15mLb21` 无 ImportError（OPT9_Recycle 继承链
   OPT9←OPT8←OPT4←OPT1_VolatilitySystem 同目录可解析；[待 WS3 结论：回收层引入的任何新
   import/文件]）。
6. REST：`curl -u <user>:<pw> http://127.0.0.1:8081/api/v1/ping` → pong（8082 同）。
7. scheduler：`deploy/monitor/scheduler.log` 出现 `scheduler up` → `job start: data refresh` →
   `job ok: data refresh`（3 币全量 1h/15m/1d+funding，预计从 20-60 分钟降至个位数分钟
   [估算，首跑实测后回填]）。
8. **回收乘子状态可见**：A 日志含 WS3 定义的乘子状态行（如 `recycle mult=1.00 regime=on
   (BTC close vs SMA100)`），且用本地 1d feather 离线复算 BTC vs SMA100 与日志 regime 一致
   [待 WS3 结论：日志行格式与复算脚本]。
9. **B funding 门控数据活**：`BTC/ETH/SOL-1h-funding_rate.feather` mtime 为当日；B 日志无
   funding 告警（数据缺失时门控按"无信息→放行"处理并告警——DEPLOY_UNRAID.md §7 口径）。
10. 监控首跑：`deploy/monitor/cron.log` 出现两腿 `OK` 行（含 dd30/ddPeak），
    `deploy/monitor/equity_daily.csv` 生成首行（两 sleeve 表头，§3.1）。

### 2.3 观察期定义

**主判据（必须满足）**：至少 **1 个完整 BTC 破线周期** = BTC 日收盘自 SMA100 上方跌破
（回收乘子 1.00 → 候选值翻转）→ 在下方持续任意时长 → 收复回到上方（乘子翻回 1.00）。
一个完整"翻转对"（off→on→off）期间：

- 乘子 >1 时段内 A **放大交易 ≥3 笔**（enter_tag/日志可统计，§3.3）；
- 每次翻转日的 A 日志状态行与 BTC/SMA100 离线复算一致（翻转无迟到/错向）；
- 期间 kill-line 未触发，或触发后已按 §2.4 协议处置并书面结案。

**次级判据（并行推进，不晚于主判则开始计时）**：常规运行 ≥8 周且 A 成交 ≥10 笔、
B 调仓/累积事件 ≥3 次、监控 dd30/ddPeak 序列无 >2 日缺口、`user_data/strategies/` 零改动
（`git status` 干净）。

**边界情形**：若 6 个月内未出现破线周期（持续牛市），主判据悬置——按"无翻转数据"出具
中期报告（只验证常规路径 + 影子模拟回收 [待 WS3 结论：是否有离线影子模式]），是否带条件
进入 G4 由所有者书面决定；不得因"等不到翻转"而修改 SMA100 定义（预注册纪律）。

### 2.4 红线与 kill-line 协议（预注册）

- **红线**：30d 滚动 DD > -20% → 停两策略容器、人工复盘（monitor_portfolio.py 语义）。
- **哨兵**：从峰 DD > -25% → 不停机但必须人工看。
- 两条阈值**保留原值，待 WS2 的 MC p95 复核后可能重校准**（§7 G4；重校准只能收紧或经
  书面论证后放宽，且生效前写入本文件修订记录）。
- **观察期内禁改策略**：`user_data/strategies/` 全部冻结；dry-run 期间发现的基础设施问题
  只能修 deploy/ 层；策略级 bug → 停机走复盘流程，禁止热修（防止借 fix 之名调参）。
- **预注册重启规则**（本会话结论）：
  1. 停机后先完成**复盘四问**并书面存档（`research_ab/postmortems/`，问题措辞为 WS4 整理，
     见 §9 披露）：① 回撤是否超出策略已知风险画像（对照回测/MC 分位）？② 是否存在实现/
     数据/基础设施 bug（对照 §4.5 清单逐项排查）？③ 逐笔抽查：实际成交与信号语义是否与
     回测一致？④ 市场形势是否属于预注册的失效条件（本次复盘即为该条件积累样本）？
  2. 四问无未闭合项后，策略转**影子模式**（dry-run 容器继续跑、继续记影子权益，但其曲线
     不作为任何 gate 依据）。
  3. **影子权益创 30d 新高**方可重启（dry-run 阶段 = 重新计入观察期；实盘阶段 = 恢复资金）。
     重启决定与影子曲线一并存档。

---

## 3. 监控适配（monitor_portfolio.py 三 sleeve → 两 sleeve）

### 3.1 代码改动点（落地时改已跟踪文件，diff 清单）

| # | 位置 | 改动 |
|---|---|---|
| 1 | `DEFAULT_BOTS` | `"http://127.0.0.1:8081,http://127.0.0.1:8082,http://127.0.0.1:8083"` → 去掉 8083 |
| 2 | `poll_once` 硬编码 `len(bots) != 3` | 改为 `len(ok) != len(bots)`（顺带消除对 3 的魔法数依赖） |
| 3 | `write_history` fieldnames | `["date","a","b","c","total"]` → `["date","a","b","total"]` |
| 4 | `poll_once` 快照行 | 去掉 `"c"` 键；日志行去掉 `C={vals[2]:.0f}` 段 |
| 5 | `drawdowns` | 无需改（读 history 的 `total`） |
| 6 | `RED_LINE_30D / REVIEW_PEAK` | 保留 -0.20 / -0.25，**旁注**：`# 待 WS2 MC p95 复核后可能重校准（ws4_deployment.md §3.2）` |
| 7 | 历史数据 | 旧 `equity_daily.csv`（三 sleeve 含 C 列）**归档**为 `equity_daily_abn_3sleeve.csv`，新文件从零起——混用会把 C 腿残值污染进 dd30 序列 |

### 3.2 阈值口径说明

-20%/30d 与 -25% 从峰哨兵保留，依据：24-26 诊断中 45/25/30 组合最深 30d 滚动 -14.4%、
from-peak -25.3%（恰好越过哨兵、未触红线）——组合形态下两阈值均有实距。**但**新组合是
64/36 + 回收（回收模拟 from-peak maxDD -26.2%~-35.1%，视系数），分布右尾更厚，
**最终阈值以 WS2 的 MC p95 复核为准**；在此之前按现值执行。

### 3.3 新增：回收状态可视化（建议 `deploy/monitor_recycle.py`，stdlib-only）

每日随监控任务跑一次，输出三指标追加到 `deploy/monitor/recycle_daily.csv`：

| 指标 | 采集途径 | 备注 |
|---|---|---|
| 乘子当前值 | A 容器日志 grep 乘子状态行（`docker logs ft-ab-a`）或 [待 WS3 结论：若 WS3 暴露 REST 可见载体（如 enter_tag 前缀 / custom_data），优先 REST] | 与 BTC vs SMA100 离线复算交叉验证 |
| 上次翻转时间 | 乘子状态行的值变化点（日志时间戳） | 翻转频率监控：连续 2 个月 >1 次/月 → REVIEW（§6 R3） |
| 累计放大交易数 | A 的 `/api/v1/trades` 中乘子>1 时段开仓计数（若 WS3 在 enter_tag 打标，直接数 tag） | G3 判据的数据源 |

同时把 opt9_forensic_program.md §4 建议的 **P2 熔断计数器**（同向止损 ≥2/24h 事件数）纳入：
从 A trades 记录统计近 24h 同向止损次数，≥2 时在日志行打 `P2-CIRCUIT` 标记
（confirm_trade_entry 拒单是静默的，只有自己数）。

---

## 4. 实盘迁移前置条件（G5 之前全部关闭）

### 4.1 Binance 子账户 ×2（强制）

- 问题：两实例共享一个合约账户时，freqtrade 以**账户总权益**计算可用余额——A 的
  `equity×risk_pct` sizing 与 B 的 `pv/TOP_N` sizing 都会把对方占用的保证金视为自己可用，
  互相污染 → 超开/杠杆失真（dry-run 的独立钱包语义掩盖了这一点）。
- 方案：主账户下建 **2 个子账户**（sub-A / sub-B），各自独立 API key，实盘 config 各绑各的。
  预算 = 划入资金，天然 64/36。

### 4.2 API 权限最小化

- 每 key 仅开 **Enable Futures**（读 + 现货/合约交易），**禁提现**；
- IP 白名单绑部署出口 IP——注意走 mihomo 代理时出口 = 代理节点出口：若节点不固定则二选一：
  固定代理出口节点，或放弃 IP 绑定但 key 只落在权限最小化的子账户上（书面记录取舍）；
- secret 只存 NAS 文件权限 600 的 env/json，不进 git（`.gitignore` 已覆盖 dry-run 状态文件，
  实盘 key 文件名加入忽略）。

### 4.3 资金划转流程（每季度/每次再平衡执行）

主账户买入 USDT → 划转至 sub-A / sub-B（64/36）→ 各子账户内部划入 USDT-M 合约保证金账户 →
按 §5.2 runbook 重启两实例。全程截图/记录到 `deploy/monitor/rebalance.log`。

### 4.4 最小资金门槛与 qty/min-notional 校验

- **最小运行资金**：[待 WS1 结论]（涉及：Binance 最小名义/步进 vs A 的 1% 风险 sizing 在
  低权益、stop_pct~7% 时 notional 过小；B 的 pv/3 目标低于 min notional 时 `custom_stake_amount`
  返回 0 → 静默不建仓）。
- 实盘前 qty/min-notional 校验步骤：
  1. `docker compose -f deploy/docker-compose.ab.yml run --rm sleeve-a-opt9` 内执行
     ccxt `load_markets()`，导出 3 币 `LOT_SIZE.stepSize / min amount` 与
     `MIN_NOTIONAL`（Binance futures 为 market 限量的 notional 字段），存档
     `deploy/monitor/exchange_limits.json`；
  2. 用 dry-run 末期 A/B 的实际 stake 分布（trades 表 `stake_amount` 分位数）对照上限/下限：
     最小 stake ≥ min_notional × 安全余量 1.2，最大 notional（权益×0.35×2x×回收乘子上限）
     ≤ 流动性可承受 [设计判断，余量值待实盘首周校准]；
  3. 实盘首周逐笔核对：拒单（insufficient funds / min notional）计数为 0 或逐笔可解释。

### 4.5 历史已知 live bug 清单及对策（映射 commit）

| # | Bug（commit） | 机理 | 部署对策 |
|---|---|---|---|
| 1 | **微秒时间戳**（6065744，run-1 实盘 -20.6% 代价） | live fill 时间带微秒精度 vs candle frame `datetime64[ms]` → pandas3 `searchsorted` raise "Cannot losslessly convert units" → bare except 吞掉 → `custom_stoploss` 返回 None（止损停在 -0.30 灾难位）+ `custom_stake_amount` 回退等分。回测免疫（candle 对齐 fill） | OPT8/OPT9 已含 `floor('ms')` 根修复——**OPT9_Recycle 必须继承 OPT9**（不得从 OPT4 直接派生绕过）；日检：止损值随交易变化、stake 呈波动率缩放（run-3 的 08:00 摘要 cron 先例，建议沿用） |
| 2 | **tz/单位不匹配**（d09ba64） | ccxt 实盘 df 是 tz-aware `datetime64[ms]`（pandas2），DB 的 Trade datetime 是 tz-naive ns → `_last_closed` 的 searchsorted ValueError 被 bare except 吞 → ATR 锚定/追踪止损 live 从未生效，止损挂死 -30%（NAS dry-run 第 1 周发现：3 笔 trendshort 持 ~6 天） | 修复已进对应策略；验收/日检：抽查止损收紧轨迹（如 -8/-11/-12% 而非 -30% 挂死）、`custom_stoploss` 零 rejected 调用；**WS3 新代码禁止 bare except 吞对齐/单位异常**（fail-loud） |
| 3 | **定价回退**（c389a98） | Binance 拒绝 ticker pricing（`use_order_book=false` 不可用） | 两 sleeve config 两侧 `entry_pricing/exit_pricing` 保持 `use_order_book: true + order_book_top: 1`（§2.1 模板已含，列为验收第 6 项前置检查项） |
| 4 | **NAS 代理**（e90b518） | bridge 网络下容器内 `127.0.0.1` ≠ 宿主机，代理必须写宿主 **LAN IP**，且 https/ws/wss 三字段都要 | config 模板已写 `192.168.73.103:7897` 三件套；部署验收：容器内 `curl -x http://192.168.73.103:7897 https://api.binance.com/api/v3/ping` 通；代理 IP 变更走 §5.4 runbook |
| 5 | **funding cache**（7ea932c） | opt_common 旧进程级 lru_cache → 运行中的 B 不重启读不到每日新 funding feather | 主干已是 mtime 感知缓存（`_funding_cache` 按 `st_mtime_ns`）；验收：首跑后次日确认 B 行为/日志反映新 funding（且 §2.2 第 9 项 mtime 检查兜底） |
| 6 | **OPT8 42d 潜伏 bug**（8d30ab8，程序中发现） | `get_analyzed_dataframe` 只留最近 1000 根 → 持仓 >~42 天时入口 candle 丢失 → fallback 裸比例被解释为相对现价的追踪止损，恰好截断趋势大赢家 | OPT9 已修（锚定 ATR 经 `set_custom_data` 一次性缓存 + `stoploss_from_open` 锚定 fallback）；**禁止 OPT8/OPT4 直接上线实盘**；日检：`open_date` 距今接近 1000h 的持仓 + `stop fallback` 告警计数 |

---

## 5. 运维例行

### 5.1 数据刷新（3 币后的变化）

- 量变：12 币 ×（1h/15m/5m/1d+funding）→ 3 币 ×（1h/15m/1d+funding）。**删除 5m 是最大节约**
  （5m 蜡烛量占原下载大头），加上币数 12→3：每日增量预计从分钟级降到秒级，全量首跑从
  20-60 分钟降到个位数分钟 [估算，首跑实测回填 §2.2 第 7 项]。
- 带宽敏感点不变：B 的 funding 门控依赖本地 feather 新鲜度（NaN→放行语义），刷新失败的处理
  见 §5.4-C。
- **scheduler.log 每日人工一眼**的纪律保留（DEPLOY_UNRAID.md §5），并加一条：
  `job FAIL: data refresh` 连续 2 日 → 停 B 容器（funding/regime 数据陈旧风险），修复后重启。

### 5.2 季度预算再平衡 runbook（手动改数字重启）

1. 时点：季度末首个 UTC 周日 00:00-00:10Z（scheduler 刷新前），并核对 A 无持仓、B 持仓贴
   近目标权重（有持仓则顺延至最近满足日；A 持仓期可 forceexit 前先人工确认——不自动砍仓）。
2. `docker compose -f deploy/docker-compose.ab.yml stop sleeve-a-opt9 sleeve-b-momregime`。
3. dry-run：改两 config 的 `dry_run_wallet` 使比例回到目标（当前总权益 T = A+B，A=0.64T、
   B=0.36T，取整）；实盘：按 §4.3 划转。**权重目标值以 [待 WS2 结论] 为准**（默认 64/36）。
4. `up -d`，复跑 §2.2 第 2/4/6/10 项验收。
5. 人工 append 一行到 `deploy/monitor/rebalance.log`：日期、再平衡前权益与权重、划转额、执行人。
- 漂移带宽：再平衡间隔期内若实际权重偏离目标 ±10pp（如 A 权益占比 >74% 或 <54%）→ 提前
  触发本 runbook [设计判断，带宽值未经模拟验证]。计算源：`equity_daily.csv` 的 a/b 列。
- 重启安全性依据：B 持仓存 db 恢复无碍；A 的锚定 ATR 在 trades 表 custom_data，重启不丢
  （OPT9 修复后的语义）。

### 5.3 灾难场景 runbook

| 场景 | 症状 | 处置 |
|---|---|---|
| A. 容器崩溃 | 容器退出；`restart: unless-stopped` 自动拉起 | 拉起后查日志与 REST ping；若崩溃循环（>3 次/小时）→ `stop` 全栈、保留 db/日志现场、按复盘四问②排查；sqlite WAL 边车（wal/shm）在 stop 后自动 checkpoint |
| B. 数据损坏（feather 坏/读失败） | 刷新 FAIL 或策略报读取错误 | 停 scheduler；删该币该 timeframe feather 单文件，`download-data --pairs <pair> -t <tf>` 单补；校验行数后重启对应实例 |
| C. funding 数据缺失 | funding feather 停更 / B 日志 funding 告警 | 门控语义 = 无信息→放行（可能高 funding 时加仓）：缺失 >24h → **停 B 容器**直至 funding 恢复；恢复后 B 免重启读到新数据（mtime 缓存） |
| D. 交易所维护/断连 | REST/WS 报错重连 | freqtrade 自动退避重连，不动栈；持续 >2h 查代理（见 E）与 Binance 公告；期间未成交挂单由 `unfilledtimeout` 10min 兜底 |
| E. 代理（mihomo）故障 | 容器网络错误但 Binance 状态页正常 | 先 `docker exec ft-ab-a curl -x ... ping` 隔离；代理不可用 → 修复代理进程；若 NAS 网络可直连，可临时删 config 代理三字段重启（直连可用性按环境，事先测一次并记录） |
| F. 磁盘满 | sqlite/feather 写失败 | 预防：`/mnt/user` 池保持 ≥20GB（DEPLOY_UNRAID.md §1）；清理 `user_data/backups` 与旧日志 |
| G. kill-line 触发 | monitor exit 2 / RED-LINE | §2.4 协议：停两策略容器（scheduler 可留）、四问、影子模式、30d 新高重启 |

### 5.4 备份

每周一次：`user_data/tradesv3_ab_*.sqlite`（stop 后拷贝或用 sqlite `.backup`）、
`deploy/monitor/*.csv`、`deploy/monitor/*.log` → 阵列第二路径 + 异地一份（rsync 即可）。
feather 数据可重建不备份（全量下载 ≤ 数分钟）。

---

## 6. 风险登记册

| # | 风险 | likelihood | impact | 缓解 |
|---|---|---|---|---|
| R1 | **B 口径差**：12 币诊断 MOT 4 vs 部署 MOT 3（诊断曲线非部署口径逐字复现） | 低（代码分析判等价，见 §1.4） | 中 | 启动前 MOT 3/4 同窗 diff=0 核验；diff≠0 则书面分析后再定 |
| R2 | **3 币宇宙削弱 A 空头腿**：A 的分散本来自 12 币波动事件；3 币（缺 DOGE/AVAX 类高波动山寨）空头触发更少、单币更集中 | 中（结构性，已知：3 币 24-26 A +89.6%/DD31.2% vs 12 币 +102.6%/42.3%） | 中 | 冻结决策接受；P2 熔断对冲同向聚集；监控 A 单体 30d DD（单体曾达 -25.1%，24-26） |
| R3 | **回收乘子在 BTC 抖动期反复翻转**（SMA100 附近锯齿）→ 放大/缩回频繁、费用与行为噪音 | 中（BTC 在 SMA100 附近震荡是常态） | 中 | [待 WS3 结论：乘子作用于新仓还是存量——若含存量调仓需评估费用]；监控翻转频率（§3.3），连续 2 月 >1 次/月 → REVIEW；不得事后加滞后带（预注册） |
| R4 | **OPT9_Recycle 是全新代码**（回收层无任何 live/回测历史，且 OPT9 系本身只有 dry-run run-3 短历史） | 中 | 高 | WS3 交付须含复现验证 + 单测；G3 完整破线周期 gate；逐笔对账；新代码禁 bare except（§4.5-2） |
| R5 | **单一交易所**（Binance）：维护、插针、ADL、规则变更 | 低-中 | 高 | kill-line/哨兵；不加杠杆（A 固定 2x、B 1x）；ADL 指标进监控为可选项；不做交易所故障期的任何"手动救仓" |
| R6 | **funding 缺失 NaN→放行**：B 在高 funding 时仍加仓/建仓 | 低（刷新自动+监控） | 中 | feather mtime 日检；缺失 >24h 停 B（§5.4-C）；告警行保留 |
| R7 | **双实例共享余额污染**（实盘若不上子账户） | 高（若违反 §4.1） | 高 | 子账户为 G5 硬前置；验收含两 key 权益独立性检查（各 REST balance 互不含对方持仓） |
| R8 | **回收 × 红线相互作用**：回收放大 A 风险预算（1.28-1.56×），bear 期连亏加深 → 红线可能早于历史模拟触发 | 中 | 高 | WS2 用 MC p95 定系数与红线终值（G4）；观察期内红线触发即执行协议，不因"回收期正常"豁免 |
| R9 | **权重漂移**：实盘无日度再平衡（run 权重），而 WS2 模拟是日度再平衡 64/36 → 实际口径偏离优化假设 | 高（必然漂移） | 低-中 | 季度再平衡（§5.2）+ ±10pp 提前触发；漂移量在监控行展示 a/(a+b) 占比 |
| R10 | **实盘-only bug 家族再现**（回测免疫路径：时间戳精度/tz/单位/1000 根窗口；共同特征 = 错误被吞后静默降级） | 中（历史上 3 次独立出现） | 高 | §4.5 清单全部映射为验收/日检；fail-loud 编码规约进 WS3 验收；08:00 摘要 cron 校验止损多样性 + stake 缩放 |
| R11 | **刷新失败静默积累**（FAIL 只在 scheduler.log，无人看 → funding/1d 陈旧 → B 用过期 regime 数据） | 中 | 中 | 每日人工一眼纪律 + 连续 2 日 FAIL 自动停 B（§5.1）；scheduler.log 纳入周备份 |
| R12 | **资金低于门槛**（sizing 低于 min_notional → 拒单或 B 静默不建仓） | 视资金而定 | 中 | [待 WS1 结论] 门槛为 G5 硬前置；§4.4 步骤 2 的分位数对照 |

---

## 7. 里程碑与 gate（判据可量化）

```
G0 文件就绪 → G1 dry-run 启动 → G2 常规 8 周 → G3 完整破线周期 → G4 MC/红线复核
→ G5 小资金实盘 → G6 分台阶加仓
```

| Gate | 内容 | 通过判据（全部满足） | 不通过处置 |
|---|---|---|---|
| G0 | 蓝图落地（§8 清单执行完毕，OPT9_Recycle 已合入 oss/） | WS3 报告验收通过；新 config/compose/scheduler 文件在位；§1.4 MOT 核验 diff=0 | 退回 WS3/WS2 |
| G1 | dry-run 启动 | §2.2 验收 10 项全绿 | 修复后重跑清单 |
| G2 | 常规运行 8 周 | A 成交 ≥10 笔；B 调仓/累积 ≥3 次；监控序列缺口 ≤2 日；策略目录零改动；funding feather 每日更新率 ≥95% | 延长至满足；出现策略级 bug → §2.4 停机流程 |
| G3 | ≥1 个完整 BTC 破线周期 | 完整翻转对 ≥1 次；放大交易 ≥3 笔；每次翻转与 BTC/SMA100 复算一致；期间红线未触发或已按协议结案；dry-run 组合 dd30 未低于 -20% | 继续观察到满足；6 个月无破线 → §2.3 边界情形报告 |
| G4 | MC/红线复核（依赖 WS2） | MC p95 maxDD、-20%/30d、-25% 哨兵、回收系数终值全部书面冻结；dry-run 曲线与回收模拟（静态 64/36 基准：30d 滚动最深 -13.0%）偏差有书面解释 | 阈值重校准后从 G2 起重算观察（若收紧）或书面放行 |
| G5 | 小资金实盘 | 资金 ≥[待 WS1 结论] 且 ≤ 目标总额 25% [设计判断]；§4.1-4.5 全关闭；首周逐笔对账：实盘成交与同时段 dry-run 信号一致性 ≥95% [设计判断]；qty/min-notional 拒单 0 或逐笔可解释 | 降资金重来或回 G4 |
| G6 | 逐步加仓 | 每台阶 +25% 资金、间隔 ≥4 周；每台阶末 dd30 未触线、对账一致、影子/dry-run 对照无未解释偏差 | 停在当前台阶观察 4 周，连续 2 次不达标 → 回 G4 复盘 |

---

## 8. 落地动作清单（本蓝图 → 实际文件；因硬性规则 1 由所有者执行）

| 动作 | 文件 | 性质 |
|---|---|---|
| 新建 | `deploy/docker-compose.ab.yml`（§1.2） | 新文件 |
| 新建 | `deploy/config_ab_a.json` / `deploy/config_ab_b.json`（§2.1）+ 凭据 patch | 新文件 |
| 新建 | `deploy/scheduler_loop_ab.sh`（§2.1.3） | 新文件 |
| 新建 | `deploy/monitor_recycle.py`（§3.3） | 新文件 |
| 修改 | `deploy/monitor_portfolio.py`（§3.1 七项 diff） | 已跟踪文件 |
| 修改 | `deploy/DEPLOY_UNRAID.md` 增加 AB 两 sleeve 章节（或新 AB 手册） | 已跟踪文件 |
| 归档 | `deploy/monitor/equity_daily.csv` → `equity_daily_abn_3sleeve.csv`；旧 ABN 栈 `down`；旧 `tradesv3_abn_*.sqlite` 保留 | 运维操作 |
| 依赖 | `user_data/strategies/oss/OPT9_Recycle.py` | WS3 交付（唯一合法新策略文件） |
| 依赖 | WS2 报告（权重/系数/MC p95）、WS1 报告（最小资金） | 占位 [待 WSx 结论] |

---

## 9. 诚实披露（设计判断 vs 验证事实）

**验证过的事实（有代码/文档/commit 依据）**
- §1.4 MOT 等价性论证基于对 `OPT1_MomRegime15mFast.py` 逐行阅读（TOP_N 槽位扫描、
  custom_stake_amount 的 min 链、类注释），**但等价性本身未跑回测验证**——故列为核验项而非结论。
- §4.5 六条 bug 机理直接引自 commit message 与 opt9_forensic_program.md，非转述二手信息。
- 24-26/21-26 全部绩效数字引自 report_2426_diagnostic.md 与 CONTEXT.md，未复算。
- opt_common 的 mtime funding 缓存与 NaN→放行语义为当前主干代码事实（7ea932c 后）。

**设计判断（未经模拟或实证）**
- 名义总额 10000（A=6400/B=3600）的绝对值；±10pp 漂移带宽；G5 的 25% 首仓与 +25%/4 周台阶；
  95% 信号一致性阈值；1.2× min-notional 安全余量——均为给定量级的工程判断，无回测依据。
- "复盘四问"的具体措辞为 WS4 对会话结论（四问 + 影子 30d 新高）的整理复原，CONTEXT.md 未
  逐字存档四问文本；若与原结论有出入，以原结论为准并修订本节。
- 3 币下 B 的截面动量退化为"全持有篮子"（rank≤3 与 rank≤9 在 3 币宇宙恒真——OPT1 注释
  自证的 3 币退化情形）：B 实际只剩 BTC>100dSMA × 自身 50dSMA × funding 三个门。
  这是已冻结决策的已知代价，mtm_daily_B3 曲线即此语义，非本蓝图新发现。
- 实盘（run 权重、真实滑点/费用、子账户）与 WS2 回收模拟（日度再平衡、回测成交假设）的
  口径差是结构性的，G3/G5 的对账步骤只能缩小不能消除该差。
- 全量下载时长"个位数分钟"、每日增量"秒级"为估算，首跑实测后回填。

**占位（依赖未完成工作流）**
- [待 WS1 结论] 最小运行资金门槛（§4.4、G5）。
- [待 WS2 结论] 64/36 与半/全回收系数终值、MC p95 复核后的红线终值（§2.4、§3.2、G4）。
- [待 WS3 结论] OPT9_Recycle 类名/继承、乘子作用域（新仓 vs 存量）、日志行格式与监控暴露
  载体、影子模式（§1.5、§2.2-8、§3.3、R3、R4）。

## 复现（本文档引用材料的获取方式）

```bash
git show 6065744 c389a98 d09ba64 e90b518 7ea932c   # live-fix 教训原始记录
cat deploy/{DEPLOY_UNRAID.md,docker-compose.abn.yml,config_sleeve_{a,b,c}.json,monitor_portfolio.py,refresh_data.sh,scheduler_loop.sh}
cat research_deepen/_dispatcher/report_2426_diagnostic.md
sed -n '84,94p' user_data/reports/opt9_forensic_program.md   # 第 4 节部署建议
```
