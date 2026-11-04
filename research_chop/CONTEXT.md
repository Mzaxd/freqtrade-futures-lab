# research_chop — 共享上下文（2026-11-04 分派）

先读 [PRE_REGISTRATION.md](PRE_REGISTRATION.md)（预注册契约，含门定义/验收标准/纪律）。

## 背景（一段话）
冻结的 AB 双 sleeve（A=OPT9_Recycle 波动率突破 70%，B=MomRegime 动量篮子 30%，3 币）已把趋势钱
赚到手（2022 大熊 AB +60.4%），但震荡期出血（2026-02-15→08-10：-27.6%，66 次合规止损）。
本线测试：能否在震荡期也捕获收益（C0 上限 / R3 防守削减 / C1 门控均值回归 / C2 智能网格）。

## 关键路径与命令

- 仓库根：D:\Code\AIQuant\freqtrade-futures-lab（Git Bash on Windows）
- freqtrade：`.venv/Scripts/freqtrade.exe`；python：`.venv/Scripts/python.exe`
- 1h/15m/5m feather + funding：`user_data/data/binance/futures/{PAIR}-{tf}-futures.feather`、
  `*-1h-funding_rate.feather`（PAIR ∈ BTC_USDT_USDT, ETH_USDT_USDT, SOL_USDT_USDT）
- 回测模板（3 币，策略放 research_chop/strategies/，sys.path 注入 oss 目录参考
  research_deepen/_dispatcher/strategies/DP_sleeves.py 开头 8 行的模式）：
  ```
  .venv/Scripts/freqtrade.exe backtesting --userdir user_data \
    --config user_data/configs/OPT7_config_12p.json \
    --strategy-path research_chop/strategies --strategy <S> \
    --timerange 20210101-20260912 \
    -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT --export trades --cache none
  ```
- MTM 重建：`.venv/Scripts/python.exe research_deepen/_dispatcher/scripts/dp_mtm.py <zip> <TAG> 2021-01-01 2026-09-13 <out_csv>`
- 门控标签（调度员已生成，全 agent 可直接消费）：`research_chop/data/regime_1h_{BTC,ETH,SOL}.csv`
  （列：date, close, mom_z, atr_pct_rank, state, g1, g2, g4；t 行只用 ≤t 数据，决策用于 t+1 起。
  门定义与锚窗口验证结论见 PRE_REGISTRATION.md §2/§2.1：G1=阴性对照，G3=失败簇主假设（R3 用），
  g2/g4=市场门（C1/C2 用，IS 上限高者入选）。生成脚本 research_chop/scripts/regime_label.py）
- 基线曲线：`user_data/logs/mtm_daily_{A3,B3}.csv`（A3=OPT4 基，出血归因用；B3=B）
- 基线 zip：`research_ab/results/hptA_base_ARL2x_*.zip`（A=OPT9_Recycle@1.21 lev2）；
  更早 3 币基线：user_data/backtest_results 08-22-30=DP_OPT4、08-24-51=DP_SleeveB（键名自查）
- 组合拼接方法：research_ab/ws2_analysis.py（日频固定权重、收益拼接、MC seed=20261103）
- 策略导入锚：A 基类 OPT9_Recycle（user_data/strategies/oss/OPT9_Recycle.py，含
  get_pair_dataframe 因果切片的范例实现）；ARL_2x 在 user_data/strategies/oss/AB_LevGrid.py

## 技术红线（历史教训，违反=结果作废）
1. 回测态 `get_analyzed_dataframe` 只回传最近 1000 根 —— 任何 >42 天回看指标必须用
   `self.dp.get_pair_dataframe()` + 手动因果切片（完成 candle 才用）。720h rank 需要
   `startup_candle_count ≥ 900`。
2. 回测串行执行；zip 产出后先读 JSON 核验 strategy 键名再 mv 到 research_chop/results/
   （并行 mv 竞态曾产生错标/损坏 zip）。
3. sizing 层读钱包用回测语义（dp_mtm 口径 INIT=10000）；跨 sleeve 资金交互会改变成交，披露即可。
4. trades JSON 里 `initial_stop_loss_abs` 是 -0.30 灾难止损；真实 sizing 止损用 `stop_loss_abs`。

## 输出
- 报告：research_chop/wsN_*.md（结论先行/数据表/复现命令/诚实披露）
- 结果：research_chop/results/（zip）、research_chop/logs/（日志与中间 csv）
- 策略/脚本：research_chop/strategies/、research_chop/scripts/
- 禁 git；禁改已跟踪文件；IS(21-23) 设计 / OS(24-26) 只裁决。
