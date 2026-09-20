# ABN 三 sleeve dry-run 部署手册（Unraid，零插件版）

> 目标：在 Unraid 上以 Docker 跑三个 freqtrade dry-run 实例（A=OPT4 45%、B=MomRegime 25%、C=NFI-Lite 30%）
> + 一个自调度任务器容器（每日数据刷新 + 组合监控）。**只做模拟盘，不连任何真实 API key。**
> 不依赖任何 Unraid 插件（不需要 User Scripts / Compose Manager——宿主机有 docker 命令即可）。
> 机器参考：i7-6700K 实测足够（N 腿 5m×12 币全指标每周期约 5-10 秒）。

## 0. 架构（4 容器，但第 4 个不是监控常驻轮询）

| 容器 | 角色 |
|---|---|
| ft-abn-a / ft-abn-b / ft-abn-c | 三个策略实例（127.0.0.1:8081-8083） |
| ft-abn-scheduler | **每日任务器**（睡眠循环，非轮询）：00:10Z 数据增量刷新；00:40Z 组合监控单次计算。所有调栈内聚在 docker-compose 里，重启自动恢复 |

## 1. 前置条件

- Unraid 6.x/7.x，SSH 可用，宿主机 `docker` 与 `docker compose` 命令可用（Unraid 7 自带 compose v2；6.x 可用 `docker-compose` 或安装静态二进制）。
- `/mnt/user/` 所在池剩余空间 ≥ 20GB。

## 2. 摆放仓库并生成凭据

```bash
cd /mnt/user/appdata
git clone <你的仓库地址> freqtrade-abn
cd freqtrade-abn
python3 - <<'PY'
import secrets, pathlib
user = "abn"                       # 自定义
pw   = secrets.token_urlsafe(16)
jwt  = secrets.token_urlsafe(32)
for p in sorted(pathlib.Path("deploy").glob("config_sleeve_*.json")):
    s = p.read_text()
    s = s.replace("CHANGEME_USER", user).replace("CHANGEME_PASSWORD", pw).replace("CHANGEME_RANDOM_SECRET", jwt)
    p.write_text(s)
    print("patched", p)
pathlib.Path("deploy/.monitor_env").write_text(f"FT_API_USER={user}\nFT_API_PASSWORD={pw}\n")
PY
chmod 600 deploy/.monitor_env
```

## 3. 启动

```bash
docker compose -f deploy/docker-compose.abn.yml pull
docker compose -f deploy/docker-compose.abn.yml up -d
docker compose -f deploy/docker-compose.abn.yml ps    # 四容器应全部 running/Up
```

> scheduler 首次启动即自动开始全量数据下载（12 币 1h/15m/5m/1d + funding，20-60 分钟），
> 完成后当日监控任务也会补跑一次。无需手工下载。

## 4. 验收（逐条过，全绿才算部署成功）

1. 版本：`docker logs ft-abn-a 2>&1 | grep -i version` → **freqtrade 2026.8**（三实例都查）。
2. 白名单：三实例日志各含 12 个交易对（BTC/ETH/SOL/BNB/XRP/ADA/DOGE/AVAX/LINK/DOT/LTC/UNI）。
3. dry-run：日志有 dry_run 标记、exchange key 为空；初始钱包 A=4500 / B=2500 / C=3000。
4. 策略加载：OPT4_VolatilitySystem / OPT2_MomRegime15mLb21 / OPT7_NFILite，无 ImportError。
5. REST 可达：`curl -u <user>:<pw> http://127.0.0.1:8081/api/v1/ping` → pong（8082/8083 同）。
6. scheduler：`cat deploy/monitor/scheduler.log` 出现 `scheduler up` 且随后有
   `job start: data refresh`；等待全量下载完成后出现 `job ok: data refresh`。
7. 监控首跑：`deploy/monitor/cron.log` 出现一条含三腿权益与 dd30/ddPeak 的 `OK` 行；
   `deploy/monitor/equity_daily.csv` 生成首行。
8. 首笔成交后（可能数天）：抽查 `curl -u ...:... "http://127.0.0.1:808X/api/v1/trades?limit=3"`。

## 5. 红线与纪律（部署后人工遵守）

- **禁止**在任何配置中填入真实交易所 API key；本部署永远 dry-run。
- **禁止**修改 `user_data/strategies/` 下任何策略文件与冻结参数。
- 每日看一眼 `deploy/monitor/scheduler.log`：`RED-LINE`（30 天滚动回撤>20%）→ 停三个策略容器、
  人工复盘后再决定；`REVIEW`（从峰值>25%）→ 不停机但必须人工看。
- 评估节奏：dry-run 至少跑 4-6 个月再谈任何变更。

## 6. 常用运维

```bash
docker compose -f deploy/docker-compose.abn.yml logs -f --tail=50 ft-abn-a
docker compose -f deploy/docker-compose.abn.yml restart sleeve-b-momregime
docker compose -f deploy/docker-compose.abn.yml down        # 全停
cat deploy/monitor/equity_daily.csv                         # 组合日频权益
tail deploy/monitor/scheduler.log                           # 每日任务结果
```

手工补跑（可选）：`deploy/refresh_data.sh`（数据）、
`python3 deploy/monitor_portfolio.py --once`（监控，需先 source deploy/.monitor_env）。

UI（可选）：当前 API 只绑 127.0.0.1；如需 FreqUI 局域网访问，把 compose 中 `127.0.0.1:808x`
改为 `808x:8080` 并确保凭据强度（改动前与所有者确认）。

## 7. 已知口径与设计说明

- B 的 funding 门控读本地 feather（回测验证语义）；scheduler 每日刷新 + mtime 感知缓存
  （opt_common）让运行中的 B 免重启读到新数据。funding 缺失时门控按"无信息→放行"处理并告警。
- 监控为日频快照口径（与回测/蒙特卡洛的红线口径一致）；不做小时内轮询是刻意的——
  红线定义在日频回撤上，加密市场小时级噪音不应触发停机决策。
- 每日数据增量同时是研究侧真样本外数据的积累（季度验收的数据源），长期保留。
