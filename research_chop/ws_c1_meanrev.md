# WS-C1 — 门控均值回归 sleeve C（CHOP_MeanRev）：IS 网格 + OS 裁决

2026-11-04 · IS=2021-01-01~2024-01-01（设计/选点唯一窗口），OS=2024-01-01~2026-09-12（只裁决）·
3 币 BTC/ETH/SOL · freqtrade 2026.8 · 费 0.0005/边 · 杠杆 2 · 1% 权益风险/笔

策略：`research_chop/strategies/CHOP_MeanRev.py`（独立第三 sleeve，与 OPT4 家族零继承）·
脚本：`research_chop/scripts/c1_{gate_check,grid_analysis,combine}.py` ·
结果：`research_chop/results/chop_c1_*.zip`（10 个，均经 JSON strategy 键名核验后 mv）·
中间曲线：`research_chop/logs/mtm_daily_C1{is,os,osg4}.csv`

---

## 0. 结论先行（三行）

1. **胜者配置（预注册 IS Calmar 标准，笔数 ≥30 全体满足）：g2_96_25**（g2 门 × Bollinger 96h ×
   2.5σ；IS Calmar -1.41、337 笔、-46.9%）。次优 g2_168_25（Calmar -1.57、271 笔）。
   **8 个网格点 IS 全部大幅亏损（-46%~-65%）——门控 band-fade 在 IS 没有任何正期望格。**
2. **C 单独 OS 表现：g2_96_25 = -49.5%（314 笔、胜率 28.7%、笔均 -15.76 USDT（名义的 -38.5bp）、
   日曲线 Sharpe -1.08 / freqtrade 逐笔口径 -1.02、maxDD 53.6%）；预注册门规则（C0 IS 上限）指向的
   g4_96_25 更差（-51.8%、191 笔、胜率 19.4%、笔均 -64.4bp）。两门 OS 皆为深度负收益，与 C0 的
   naive 负上限方向一致（§6.1 警报未触发，因为 C1 OS 不为正——是不一致地差）。**
3. **AB+C 组合结论：双验收全部 FAIL。** wC∈{0.05,0.10,0.15} 下 OS Sharpe 0.847/0.808/0.763 均
   低于 AB 基线 0.879（验收 A 失败）；OS 震荡窗口斜率改善 -3.6/-7.2/-10.8pp（年化），远低于
   +3pp 要求（验收 B 失败）。g4 交叉核验同样双 FAIL（Sharpe 0.787@wC=0.10、斜率 -8.1pp）。
   **C1 判定为不采纳：负期望不是"门没选好"，而是"1h 越带反向"骨架本身（与 C0 结论互相印证）。**

---

## 1. 策略与门实现（预注册 §2 逐字执行）

- **timeframe 1h，startup_candle_count=900**（mom_z 需 72h、atr_pct_rank 需 720h 全窗，900 保证每个
  决策行看到完整尾随窗）。
- **门信号在 populate_indicators 内对自身 dataframe 现算**（回测态该参数为全历史，安全；全程未用
  get_analyzed_dataframe）。公式逐字复刻预注册 §2 / regime_label.py：
  `mom_z = log(close).diff(72) / (vol_12h·√72)`；`atr_pct_rank = (TR.rolling(14).mean()/close)
  .rolling(720, min_periods=240).rank(pct=True)`；**g2 = |mom_z|<1.25 AND atr_pct_rank≥0.90**；
  **g4 = 过去 240h 内 ≥90% 小时 |mom_z|<1.25**。类参数 `gate ∈ {"g2","g4"}`。
- **入场**：Bollinger(period∈{96,168}, ndev∈{2.0,2.5}, SMA)——收盘越出下轨且门 ON → 次根做多；
  越出上轨且门 ON → 次根做空。can_short=True。
- **退出三层**：(a) 回中轨（populate_exit_trend：close≥bb_m 平多 / ≤bb_m 平空）；(b) 持仓 48h 时间
  止损（**custom_exit** 返回 `mr_time_48h`，freqtrade 官方逐根回调接口，此为披露的用法）；(c) 初始
  ATR 止损 1.5×ATR(14) 锚定信号柱（**custom_stoploss + stoploss_from_absolute**，OPT7_NFILite 范式；
  绝对价固定、不追踪；ATR 取 TR 的 SMA(14)——与门特征 atr_pct 同核，非 Wilder talib ATR，披露）。
  灾难 stoploss=-0.15。
- **sizing**：stop_pct = max(1.5×ATR/信号柱收盘, 0.5% 下限)；notional = equity×1%/stop_pct；
  stake = notional/2（杠杆 2），上限 equity×35%（margin_cap）。position_adjustment_enable=False；
  MOT 用 config 默认（4，实际 3 币 → 上限 3）。
- 回调内 ATR/价格读取用 `dp.get_pair_dataframe` + 严格因果切片 + 长度键控缓存（OPT9_Recycle 范式，
  规避 1000 根截断 bug）。

**门一致性核验（预注册 §6.2）**：`c1_gate_check.py` 直接实例化策略类、对全量 feather 跑
populate_indicators，与调度员标签 `research_chop/data/regime_1h_{BTC,ETH,SOL}.csv` 在 **15 个抽样窗**
（3 币 × IS/OS 共 5 窗，含 2021-05、2022-06~09、2023-10~12、2024-04~07、2026-02-15~08-10 出血窗）
逐点比对：mom_z/atr_pct_rank 差 ≤1e-15（浮点噪声级），**g2/g4 布尔完全一致（15/15 窗）**。

## 2. IS 网格全景（8 点，2021-01-01~2024-01-01，串行执行）

| 配置 | 笔数 | 总收益% | CAGR% | Sharpe | **Calmar** | maxDD% | 胜率% | 笔均净(USDT) | 笔均净(名义bp) | 费用+资金费/毛利 | 止损退出% | 中轨% | 时间% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| g2_96_20 | 475 | -59.4 | -26.0 | -1.28 | -1.66 | 62.5 | 30.1 | -12.51 | -55.9 | 0.097 | 66.9 | 18.3 | 14.3 |
| **g2_96_25 ★胜者** | **337** | **-46.9** | **-19.0** | **-0.95** | **-1.41** | **58.2** | **30.3** | **-13.92** | **-66.9** | **0.098** | **66.8** | **16.9** | **15.7** |
| g2_168_20 | 413 | -64.6 | -29.2 | -1.44 | -1.71 | 65.9 | 27.1 | -15.64 | -74.8 | 0.106 | 69.5 | 9.7 | 20.3 |
| g2_168_25（次优） | 271 | -50.1 | -20.7 | -0.97 | -1.57 | 55.6 | 26.6 | -18.50 | -83.8 | 0.114 | 69.4 | 8.5 | 21.8 |
| g4_96_20 | 329 | -49.8 | -20.5 | -0.98 | -1.66 | 52.2 | 25.8 | -15.12 | -37.5 | 0.155 | 72.9 | 18.8 | 8.2 |
| g4_96_25 | 215 | -48.3 | -19.7 | -0.87 | -1.57 | 53.5 | 22.3 | -22.46 | -34.5 | 0.170 | 77.2 | 13.5 | 9.3 |
| g4_168_20 | 291 | -48.7 | -20.0 | -0.97 | -1.59 | 53.6 | 25.4 | -16.75 | -42.3 | 0.156 | 73.5 | 13.7 | 12.7 |
| g4_168_25 | 200 | -46.0 | -18.6 | -0.87 | -1.72 | 46.7 | 23.5 | -22.99 | -53.2 | 0.169 | 75.0 | 9.5 | 15.0 |

- 选择标准 = IS Calmar 最高且笔数 ≥30：**g2_96_25**（全部 8 点笔数 200-475，门槛远超，无统计意义缺口）。
- 门级对比（IS Calmar 最佳）：g2 -1.41 > g4 -1.57；两门皆深度为负——"上限高者"是两害相权。
- 胜率 22-30% + ~2/3 止损退出：门窗口内的越带延续（crash continuation）让 1.5×ATR 止损被反复打穿
  （IS 最差单笔 -31.9% 为跳空穿越止损；OS 最差 -14.4%）。最大连亏 IS 21 笔 / OS 22 笔。
- 平均持仓 IS 17.8h / OS 16.6h（48h 时间止损有效兜尾）。

## 3. OS 裁决（预注册 §4 C1 验收；只跑 IS 胜者 + 门规则交叉核验）

**规则冲突的诚实处理（重要披露）**：预注册 §2.1 的门选择规则是"IS 上限高者入选"——C0（本轮完成后
可用）量化后指向 **g4**（naive 上限 3 币等权 -20.9% vs g2 -60.3%）；而本任务书给定且先于 OS 执行的
选择标准是"IS Calmar 最高"——指向 **g2**（-1.41 vs -1.57，边缘极小且两者皆灾难性为负）。处置：
主裁决按任务书标准跑 **g2_96_25**；同时按预注册门规则补跑 g4 的 IS 最优点 **g4_96_25** 作交叉核验
（两点均已在预注册 8 点网格内、选择只用 IS 数据、无任何参数回头修改；OS 各只运行一次）。

### 3.1 验收 A：OS Sharpe(AB+C) ≥ OS Sharpe(AB) —— 全部 FAIL

| 配置（OS 2024-01-02~2026-09-12，985 收益日） | 总收益% | 年化% | **Sharpe** | maxDD% |
|---|---:|---:|---:|---:|
| AB 基线（0.7·A3 + 0.3·B3） | +76.4 | +23.4 | **0.879** | -27.8 |
| C 单独（g2_96_25） | -49.5 | -22.4 | -1.078 | -53.9 |
| C 单独（g4_96_25，交叉核验） | -50.6 | -23.0 | -1.818 | -57.2 |
| AB+C wC=0.05 | +67.4 | +21.1 | 0.847 ✗ | -26.6 |
| AB+C wC=0.10 | +58.8 | +18.7 | 0.808 ✗ | -25.3 |
| AB+C wC=0.15 | +50.4 | +16.4 | 0.763 ✗ | -23.9 |
| AB+Cg4 wC=0.10（交叉核验） | +57.4 | +18.3 | 0.787 ✗ | -26.2 |

### 3.2 验收 B：OS 震荡窗口斜率改善 ≥ +3pp —— 全部 FAIL

震荡日集：3 币任一在 **前一日**（shift(1)，因果）有 ≥1 小时 g2∪g4 ON → 当日计为震荡日
（985 日中 497 日；BTC-only 敏感性口径 320 日）。斜率 = 组合在震荡日的日均收益
（×365.25 折年化为裁决口径，日均值另列）：

| 配置 | 震荡日斜率 bp/日 | 折年化% | 改善(vs AB，年化 pp) |
|---|---:|---:|---:|
| AB 基线 | 8.92 | +32.6 | — |
| AB+C wC=0.05 | 7.93 | +29.0 | **-3.6 ✗** |
| AB+C wC=0.10 | 6.95 | +25.4 | **-7.2 ✗** |
| AB+C wC=0.15 | 5.96 | +21.8 | **-10.8 ✗** |
| AB+Cg4 wC=0.10（交叉核验） | 6.70 | +24.5 | **-8.1 ✗** |

（BTC-only 日集敏感性：AB 斜率 7.55 bp/日，wC=0.10 的 C 贡献 -7.95pp，结论不变。）
**注**：AB 基线自身在 OS 震荡日的斜率为**正**（+32.6% 年化）——C0 已证明 A3 出血几乎全部落在
g2/g4 OFF 日（ON 日出血 ≈0），故"用 C 补震荡日"的前提本身不成立；C 只是把负收益叠加进来。

### 3.3 判定

**C1 双验收全 FAIL（两门、三档 wC、双日集口径均失败）→ sleeve C 不采纳，wC 任一档都不进入组合。**

## 4. C 单独经济性（任务要求的口径）

| 窗 | 配置 | 笔数 | 胜率% | 笔均净收益 | 笔均净(名义bp) | 费用(USDT) | 资金费(USDT) | (费+资金费)/毛利 | 总收益% | maxDD% |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| IS 21-23 | g2_96_25 | 337 | 30.3 | -13.92 | -66.9 | 739 | 268 | 0.098 | -46.9 | 58.2 |
| OS 24-26 | g2_96_25 | 314 | 28.7 | -15.76 | -38.5 | 970 | 212 | 0.112 | -49.5 | 53.6 |
| OS 24-26 | g4_96_25 | 191 | 19.4 | -27.12 | -64.4 | 806 | 112 | 0.184 | -51.8 | 57.2 |

- **§6.3 边缘检查：OS 笔均净利为 -38.5bp（名义），远低于 2×往返费率 20bp 的警戒线——不是"边缘过薄"
  而是负期望**（IS 更差：-66.9bp）。费用+资金费合计约占毛利的 10-18%，但问题根源是 2/3 交易被
  1.5×ATR 止损打出的亏损尾部，不是费率。
- OS 分币（g2_96_25）：BTC 113 笔 -1051 / ETH 110 笔 -3662 / SOL 91 笔 -235；多头 216 笔 -3298 /
  空头 98 笔 -1649——亏损不偏向单边或单币，是骨架性负期望。

## 5. 交叉核验（预注册 §6）

1. **上限核验（§6.1）**：C0 已完成（本轮运行中出现，`ws_c0_ceiling.md`）。naive band-fade 上限
   （扣费、1x、逐币独立）IS 3 币等权：g4 -20.9% / g2 -60.3%；OS：g4 -41.6% / g2 -26.2%。
   C1 OS 实绩与之的比例：g2_96_25 **-49.5% ≈ naive OS 等权的 1.9 倍差**；g4_96_25
   **-51.8% ≈ 1.2 倍差**。C1 OS 显著为**负**（非正）→ §6.1 过拟合警报**不触发**；方向与 C0
   "桌上没有 naive 均值回归的钱"完全一致。口径差披露：naive 是 1x 固定名义、无 ATR 止损、
   逐币独立起算；C1 是 lev2 + 1% 风险 sizing（复利钱包）+ 1.5×ATR 止损 + 48h 时间止损 + 含
   funding，两者数值不可直接 1:1，比例仅作量级对照。
2. **门重叠核验（§6.2）**：见 §1——15 个抽样窗逐点一致（机器精度级）。
3. **成本核验（§6.3）**：见 §4——已标注，且为负期望。
4. **红线复核（§6.4，调度员职责）**：本报告未做 MC（见披露 6），单路径 OS 下 AB+C 的 30d 滚动
   maxDD（-25%~-27%）未超过 AB 基线 -27.8%，但因验收 A/B 已双 FAIL，不构成采纳依据。

## 6. 诚实披露

1. **前视防护**：门与信号全部在 populate_indicators 的全历史 dataframe 上现算（回测态安全）；
   回调（custom_stoploss/custom_stake_amount）用 get_pair_dataframe + 严格因果切片（信号柱 =
   开仓柱前一根已收盘柱），未用 get_analyzed_dataframe（1000 根截断风险）。ATR 锚定信号柱开盘价，
   sizing 用信号柱收盘价（OPT7 范式原样，±1 根 OHIO 差异披露）。dp_mtm 重建的逐小时路径误差
   p95 ≈ 81-83 / max ≈ 175-179 USDT（1 万本金口径，PRT 方法继承的近似，日曲线影响远小于策略亏损量级）。
2. **门实现一致性**：与调度员标签 CSV 15 窗逐点一致（§1）；g4 的分数定义（240h 内 ≥90% G1，
   min_periods=240）按预注册 §2 迭代版执行。
3. **选择效应与规则冲突**：8 点网格的"胜者"是在全体为负中选最不差者（Calmar -1.41 vs 全体
   -1.41~-1.72）——胜者本身无正期望，IS 选择标准的分辨力接近噪声。门选择规则存在两版（任务书
   IS-Calmar vs 预注册 §2.1/C0 IS-上限），结论对规则选择稳健（两门 OS 皆 -50% 量级、双验收皆 FAIL），
   处置过程已在 §3 开头全量披露。IS 网格只挑 Calmar，未做多重比较惩罚——鉴于结论是负的，
   该风险只影响"哪个配置最不差"的排序，不影响"不采纳"判定。
4. **A3 口径差**：AB 基线的 A 侧用 mtm_daily_A3.csv = **OPT4 基参考曲线**（实际冻结包 A 是
   OPT9_Recycle@1.21/ARL_2x，zip 在 research_ab/results/）。C0 §6.3 已披露两者出血时点结构未核验
   一致；AB 基线 OS Sharpe 0.879 是 A3 口径数字，换 OPT9 口径会移动基线水平，但 C 的贡献是
   确定性负值（-49.5%），wC>0 必然拖累的方向性结论对基线口径稳健。
5. **费用与成交假设**：全部按 taker 0.0005/边（maker 也按 taker 计，保守）；1h 开盘价成交、无
   滑点模型；funding 按实际费率逐时计入。灾难止损 -15%（profit ratio，含杠杆）作为 ATR 止损的
   背板，IS 最差单笔 -31.9% 说明极端跳空下背板也会被穿越（爆仓口径未建模维护保证金追缴）。
6. **单路径未做 MC**：OS 只有一条实现路径，未做块自助 MC 的 p95 30dDD 复核（调度员 §6.4 职责）；
   在 C 单独 Sharpe -1.0~-1.1、笔均负 38-67bp 的量级下，MC 不太可能翻转"不采纳"，但组合层面
   wC 的最优让渡比例如未来重启需补 MC。
7. **组合口径**：日频固定权重收益拼接（ws2 方法），C 曲线来自 dp_mtm（INIT=10000 独立起算，
   跨 sleeve 无资金交互）；wC 从 A/B 按比例让渡（(1-wC)·AB + wC·C）。OS 末端 1 笔 ETH 持仓被
   force_exit（+0.89%），IS 无残留持仓。
8. **窗口纪律**：IS 只用于设计与选点；OS 每配置只运行一次（g2_96_25 主裁决、g4_96_25 门规则
   交叉核验），无回头改设计。

## 7. 复现命令

```bash
cd D:/Code/AIQuant/freqtrade-futures-lab
# 门一致性核验（15 窗）
.venv/Scripts/python.exe research_chop/scripts/c1_gate_check.py
# IS 网格（8 点串行；S ∈ {g2_96_20,g2_96_25,g2_168_20,g2_168_25,g4_96_20,g4_96_25,g4_168_20,g4_168_25}）
.venv/Scripts/freqtrade.exe backtesting --userdir user_data \
  --config user_data/configs/OPT7_config_12p.json \
  --strategy-path research_chop/strategies --strategy CHOP_MR_$S \
  --timerange 20210101-20240101 \
  -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT --export trades --cache none
.venv/Scripts/python.exe research_chop/scripts/c1_grid_analysis.py          # IS 表+选点
# OS（主裁决 g2_96_25；门规则交叉核验 g4_96_25 同式换 --strategy 与 chop_c1_os_g4_96_25 名）
.venv/Scripts/freqtrade.exe backtesting --userdir user_data \
  --config user_data/configs/OPT7_config_12p.json \
  --strategy-path research_chop/strategies --strategy CHOP_MR_g2_96_25 \
  --timerange 20240101-20260912 \
  -p BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT --export trades --cache none
.venv/Scripts/python.exe research_deepen/_dispatcher/scripts/dp_mtm.py \
  research_chop/results/chop_c1_os_g2_96_25.zip C1OS 2024-01-01 2026-09-13 research_chop/logs/mtm_daily_C1os.csv
.venv/Scripts/python.exe research_chop/scripts/c1_combine.py               # OS 裁决+组合表
```

产物清单：`research_chop/results/chop_c1_is_{8 配置}.zip`、`chop_c1_os_g2_96_25.zip`、
`chop_c1_os_g4_96_25.zip`（各带 .meta.json，键名核验后唯一命名 mv）；
`research_chop/logs/c1_is_grid_summary.csv`、`c1_os_adjudication.csv`、`mtm_daily_C1{is,os,osg4}.csv`。
