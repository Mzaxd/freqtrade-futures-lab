# LV1 预注册 — SlowA_12h 放大拐点(2026-11-07,跑任何回测之前写定)

Charter: research_lowvol/CONTEXT.md(S1-S5 冻结,不许改)。本轮变体清单 **4 点**(任务书上
限 5),全部跑、全部披露,不许事后加。不跑 hyperopt、不做参数网格;risk_pct 是账本 §3.6
确认的"唯一真拨盘",本清单只动它和宇宙宽度两个结构自由度。

## 变体清单(预声明,固定)

| # | 类名 | 文件 | 相对冻结 SlowA_12h(r1) 的唯一改动 | MOT | pairs | 备注 |
|---|------|------|--------------------------|-----|-------|------|
| 0 | SlowA_12h(基线,不重跑) | slowa_12h.py(已有,勿改) | — | 3 | BTC/ETH/SOL | zip=2026-11-07_08-04-48,口径重算入表 |
| 1 | SlowA_12h_r2 | slowa_12h_r2.py | risk_pct 0.01→0.02 | 3 | BTC/ETH/SOL | 拨盘 ×2 |
| 2 | SlowA_12h_r3 | slowa_12h_r3.py | risk_pct 0.01→0.03 | 3 | BTC/ETH/SOL | 拨盘 ×3(找拐点/非线性处) |
| 3 | SlowA_12h_12p | slowa_12h_12p.py | 宇宙 3→12 币(risk 仍 0.01) | 12 | lab 冻结 12 币白名单(见下) | 分散效应 |
| 4 | SlowA_12h_12p_r2 | slowa_12h_12p_r2.py | 12 币 + risk 0.02 | 12 | 同上 | 分散×拨盘(若 #3 跑通) |

- 12 币白名单(lab 既有口径,OPT7_config_12p.json / 12币等权基线同源):BTC/ETH/SOL/BNB/XRP/ADA/DOGE/AVAX/LINK/DOT/LTC/UNI。数据已验证:12 币 1h feather + funding 全部覆盖 2020-07/09 → 2026-11-07,无缺口 → **不需要降级 3 币**。
- MOT(12p)=12 预先固定:并发放开,仓位纪律完全交给 A 家族自带的 risk sizing + margin_cap 0.35(这是"同结构、宽宇宙"的自然直译;3 币基线 MOT=3 本来就等于 pairs 数)。此选择记 1 个自由度,入多重检验披露。
- 其余全部同上轮:`config_futures.json`、wallet 10000、fee 0.0005、timerange 20210101-20261107、`--cache none`、strategy-path oss、含 funding。

## 预期与判读框架(先写死,防事后合理化)

1. **线性区假设**:risk 1→2→3 若收益与 DD 近似等比放大(对数线性),则拨盘可任意缩放,
   LV2 装配可放心用 risk 做连续权重;偏离处(超线性 DD / 强平增多 / margin_cap 0.35 触顶 /
   P2 熔断改变事件集)即为拐点,如实报告位置与机制。
2. **12 币假设**:币间相关 0.76-0.79 → 分散收益有限;预期 25/26 略强于 3 币(更多事件)、
   DD 不显著平滑;若反而更差,如报告(扩池在 A 家族的既有教训)。
3. **S1-S4 判定口径**:逐年收益取 wallet 曲线 YE first/last,**末年锚定 final_balance**
   (修正上轮报告 2026 +18.3 的已知少计:3 笔 force_exit 未入 feather 末端,锚定后基线 2026=+21.3);
   maxDD 主口径 = freqtrade `max_drawdown_account`;dd30 = 日线 30d 滚动最差;强平 =
   exit_reason=='liquidation'(与 force_exit 分列,修正上轮把 3 笔 force_exit 记作"强平"的误标)。
4. 全部结果(含失败/难看)入 report.md,不做任何清单外补跑。

## 预算与降级

单次回测若超 20 分钟:砍 #2(r3)并注明(拐点可用 r1/r2 两点 + 机制分析部分推断)。
其余不砍。
