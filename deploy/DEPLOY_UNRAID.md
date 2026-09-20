# ABN 三 sleeve dry-run 部署手册（Unraid）

> 目标：在 Unraid 上以 Docker 跑三个 freqtrade dry-run 实例（A=OPT4 45%、B=MomRegime 25%、C=NFI-Lite 30%）
> + 一个组合监控容器。**只做模拟盘，不连任何真实 API key。**
> 机器参考：i7-6700K 实测足够（N 腿 5m×12 币全指标每周期约 5-10 秒）。

## 0. 前置条件

- Unraid 7.x，已装 Docker；建议装 **Docker Compose Manager** 插件（Apps 搜索）。
- 仓库在本机有远端（GitHub 等）可 `git clone`；或从开发机 SMB/SCP 整目录拷贝到 `/mnt/user/appdata/`（注意：`user_data/data/` 在 git 里不存在，见 §4）。

## 1. 摆放仓库并生成凭据

```bash
cd /mnt/user/appdata
git clone <你的仓库地址> freqtrade-abn
cd freqtrade-abn
# 三个配置里的 CHANGEME_* 必须替换（保持三份一致，监控只认一套）：
python3 - <<'PY'
import re, secrets, pathlib
user = "abn"                       # 自定义
pw   = secrets.token_urlsafe(16)
jwt  = secrets.token_urlsafe(32)
for p in pathlib.Path("deploy").glob("config_sleeve_*.json"):
    s = p.read_text()
    s = s.replace("CHANGEME_USER", user).replace("CHANGEME_PASSWORD", pw).replace("CHANGEME_RANDOM_SECRET", jwt)
    p.write_text(s)
    print("patched", p)
pathlib.Path("deploy/.monitor_env").write_text(f"FT_API_USER={user}\nFT_API_PASSWORD={pw}\n")
PY
chmod 600 deploy/.monitor_env
```

## 2. 启动

```bash
cd /mnt/user/appdata/freqtrade-abn
docker compose -f deploy/docker-compose.abn.yml pull
docker compose -f deploy/docker-compose.abn.yml up -d
docker compose -f deploy/docker-compose.abn.yml ps
```

四个容器：`ft-abn-a`（端口 127.0.0.1:8081）、`ft-abn-b`（:8082）、`ft-abn-c`（:8083）、`ft-abn-monitor`。

## 3. 验收（逐条过，全绿才算部署成功）

1. 版本：`docker logs ft-abn-a 2>&1 | grep -i version` → **freqtrade 2026.8**（三个容器都查）。
2. 白名单：日志中出现 12 个交易对（BTC/ETH/SOL/BNB/XRP/ADA/DOGE/AVAX/LINK/DOT/LTC/UNI USDT 永续）。
3. dry-run：每个容器日志有 `dry_run` 标记且 exchange key 为空；`Wallets` 初始额 A=4500 / B=2500 / C=3000。
4. 策略加载：日志 strategy 名分别为 OPT4_VolatilitySystem / OPT2_MomRegime15mLb21 / OPT7_NFILite，无 ImportError。
5. REST 可达：`curl -u <user>:<pw> http://127.0.0.1:8081/api/v1/ping` → `{"status":"pong"}`（8082/8083 同）。
6. 监控：`docker logs ft-abn-monitor` 首小时内应打印一条含三腿权益与 dd30/ddPeak 的 OK 行。
7. 首笔成交后（可能要等数天）：抽查某实例 `curl -u ...:... http://127.0.0.1:808X/api/v1/trades?limit=3`。

## 4. 数据刷新（Sleeve B 的 funding 门控依赖本地数据）

`user_data/data/` 不在 git 里。首次部署后先全量拉一次，之后每日增量：

```bash
docker compose -f deploy/docker-compose.abn.yml run --rm sleeve-a-opt4 \
  download-data --userdir user_data --config user_data/configs/OPT7_config_12p.json \
  --timerange 20210101- --timeframes 1h 15m 5m 1d
```

之后用 **User Scripts** 插件每日调度 `deploy/refresh_data.sh`（脚本会自动走 docker compose）。
> 已知口径差：若 funding 数据缺，B 的门控按"无信息→不拦截"处理（NaN-passes），行为趋保守披露。

## 5. 红线与纪律（部署后人工遵守）

- **禁止**在任何配置中填入真实交易所 API key；本部署永远 dry-run。
- **禁止**修改 `user_data/strategies/` 下任何策略文件与冻结参数。
- 监控红线：`deploy/monitor/alerts.log` 出现 `RED-STOP`（30 天滚动回撤>20%）→ 停全部容器、人工复盘后再决定；`REVIEW`（从峰值>25%）→ 不停机但必须人工看。
- 评估节奏：让 dry-run 至少跑 4-6 个月再谈任何变更；策略层面的结论以主仓库研究报告为准。

## 6. 常用运维

```bash
docker compose -f deploy/docker-compose.abn.yml logs -f --tail=50 ft-abn-a
docker compose -f deploy/docker-compose.abn.yml restart sleeve-b-momregime
docker compose -f deploy/docker-compose.abn.yml down          # 全停
cat deploy/monitor/equity_daily.csv                           # 组合日频权益
```

UI（可选）：浏览器访问 FreqUI —— `http://<NAS-IP>:8081` 会由容器 8080 映射（当前仅绑定 127.0.0.1，
如需局域网访问把 compose 里的 `127.0.0.1:808x` 改成 `808x:8080`，并确保凭据强度）。
