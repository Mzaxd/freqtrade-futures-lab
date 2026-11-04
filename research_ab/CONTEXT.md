# research_ab — AB 双 sleeve + 动态调仓 路径研究工作区（2026-11-03 分派）

## 已冻结的决策上下文（本会话得出，各 agent 共享）
- 路径：AB 两 sleeve 组合，3 币宇宙 BTC/ETH/SOL（Binance USDT-M 永续），动态资金回收：
  当 BTC 日收盘 < SMA100（即 B 的牛熊开关关闭时），A 的仓位 × 回收系数（候选：半回收 1.28 / 全回收 1.56）。
- Sleeve A = OPT4_VolatilitySystem（user_data/strategies/oss/，1h 双向波动率突破，1% 权益风险
  sizing（notional = equity×risk_pct/stop_pct），2x 杠杆，margin_cap=0.35/笔，MOT 4）。
- Sleeve B = OPT2_MomRegime15mLb21（15m 纯多头动量篮子：持有 21 天动量前 3 名，BTC>100dSMA 开关，
  自身 50dSMA 过滤，跌出前 9 名轮动退出，无止损，funding gate 0.0005，TOP_N=3）。
- 已有日度 MTM 曲线（21-26，3 币，OPT4 基）：user_data/logs/mtm_daily_{A3,B3,S3,L3}.csv
  （A3=A 原版, B3=B, S3=A 只空, L3=A 只多）。12 币拼接曲线：
  research_deepen/portfolio/results/mtm_daily_{A,B,N}.csv + research_deepen/_dispatcher/results/mtm_daily_{A,B,N}_2426.csv。
- 回测模板（3 币）：.venv/Scripts/freqtrade.exe backtesting --userdir user_data
  --config user_data/configs/OPT7_config_12p.json --strategy-path <oss|research_deepen/_dispatcher/strategies>
  --strategy <S> --timerange 20210101-20260912 -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT
  --export trades --cache none
- MTM 重建：.venv/Scripts/python.exe research_deepen/_dispatcher/scripts/dp_mtm.py <zip> <TAG> 2021-01-01 2026-09-13 <out_csv>
- 既有结果 zip（JSON 内 strategy 键名，用前自行核对）：06-52-44=OPT9(12p), 08-22-30=DP_OPT4(3p),
  08-24-51=DP_SleeveB(3p), 08-21-58=DP_NFILite(3p), 08-58-05=OPT4_ShortOnly(3p), 08-58-08=OPT4_LongOnly(3p)。
- 会话关键数字：corr(A,B)=0.453；回收模拟（用 B 实际暴露）：静态 64/36 +2767%/CAGR 80.1%/Sharpe 1.97/
  maxDD -26.2%/30d滚动 -13.0%；全回收 +3858%/90.6%/1.94/-35.1%/-13.8%；半回收 +3284%/85.5%/1.96/-30.8%/-13.1%。
- 风控红线：30d 滚动 DD > -20% 停机（monitor_portfolio.py），从峰 -25% REVIEW 哨兵。
- 纪律：入场逻辑不可动（falsified-direction）；参数选择须预注册，网格结果必须披露选择效应。

## 所有 agent 的硬性规则
1. 禁止 git commit/push；禁止修改任何已跟踪文件；新文件只写入 research_ab/**（WS3 另可写
   user_data/strategies/oss/OPT9_Recycle.py）。
2. 每个回测完成后立即把 zip mv 到 research_ab/results/（唯一命名），日志写 research_ab/logs/（前缀区分）。
3. 数据覆盖至 2026-09-14；窗口统一 20210101-20260912。
4. 报告写 research_ab/wsN_*.md：结论先行、数据表、复现命令、诚实披露（口径/近似/选择效应）。

## 工作流分派
- WS1 最小运行资金 → ws1_min_capital.md
- WS2 AB 比例 × 回收系数 × 时期/市场形势 → ws2_weights_regimes.md
- WS3 自动调仓实现与验证（OPT9_Recycle）→ ws3_recycle_impl.md
- WS4 部署蓝图 → ws4_deployment.md
