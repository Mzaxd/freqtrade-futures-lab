# 阶段 7 终版报告：遗珠计划（Salvage Program）— 2026-09-12

章程：[phase7_salvage_charter.md](phase7_salvage_charter.md)。五线分报告：[S1 NFI](phase7_s1_nfi.md) · [S2 Reversion](phase7_s2_reversion.md) · [S3 Supertrend](phase7_s3_supertrend.md) · [S4 FreqAI](phase7_s4_freqai.md) · [S5 Router](phase7_s5_router.md)。
协议核心创新：**分家族 holdout**——2024-26 只对 VolSys 家族烧毁，S1-S5 五族首次获得真正的一次性 holdout；11 新币对非 VolSys 族仍是干净验证轴。S4 中途死亡由 S4b 续命收尾（孤儿进程产物回收，零重复计算浪费）。

## 总裁定：3 过 2 灭，两颗真遗珠 + 一个降级遗产

| 线 | 裁定 | 核心数字 | 一句话 |
|---|---|---|---|
| S1 NFI-Lite | **过门** | 池 +63.5%/**DD 4.0%**/PF 2.35/Sharpe 2.21；新币 +54.7% 11 币全正；holdout +1.0%（7 笔）；corr(A)=-0.01 | **危机收割凸性 sleeve**——DCA 依赖被逐家族消融破解（家族 120 唯一亏损=直接实证），无 DCA 也成立 |
| S3 SuperDD | **过门** | 池 DD 79.0→**27.5%**；新币 -24.6→+34.2%（风险结构版才迁移）；holdout +18.8%/DD 24.1% | 风险治理立线：8×ATR 宽锚定有效，一切窄止损/追踪毁这个慢共识信号族 |
| S5 Router 2.0 | 过门但降级 | 变体 A 池 +135%/DD 17.3%；但静态 sleeve 碾压全路由 | **遗产= turbulent 暂停 overlay**（新币轴全面优于 OPT4 单体），骨架弃用；v1"唯一 OOS 为正"系 3 币顺风窗局部现象 |
| S2 Reversion v2 | 灭 | 新币 -12.2%（老币利润 UNI 单币占 168%）；"funding 收入"97% 集中单事件 | alpha 不可迁移，诚实淘汰；corr≈0 的月度形态留档 |
| S4 FreqAI | 灭 | 2023 段最优 -1.99%（PF 0.94）；自有特征重要性仅 2.76%；费率墙 | 改善=少交易减亏非 alpha 创造；ML 线归档，翻案需换结构非调参 |

## 组合层更新（三 sleeve 数学，36 个月口径，月度闭仓聚合近似）

corr 矩阵：A-B 0.096 / A-N 0.216 / B-N 0.257（全低）。

| 组合 | 总收益 | maxDD | Calmar |
|---|---|---|---|
| A 单独 | +1495.8% | 12.9% | 11.25 |
| A+B 50/50 | +1798.1% | 9.82% | 16.26 |
| **A+B+NFI 40/40/20** | **+1129.2%** | **6.92%** | **18.15** |
| A+B+NFI 等权 | +807.8% | 4.98% | 20.99 |

**推荐配置：A+B+NFI = 40/40/20**（NFI-Lite 定位组合保险，20% 权重换 DD -30%）；等权版是 Calmar 极大值但让渡利润过多。注意口径披露：均为池内（2021-23+VAL 拼 36 个月）近似；NFI-Lite 的池外表现（holdout 7 笔）证明其触发稀疏性——**它的价值在崩盘月，评估窗口没含崩盘是低估而非高估**。

## 新资产清单与部署建议

1. **NFI-Lite**（`OPT7_NFILite.py`）：建议进 dry-run 第三实例（低频、几乎零运维），配置需按 S1 报告的冻结参数生成
2. **turbulent 暂停 overlay**（S5）：OPT4 的可选增强——建议等 Sleeve A dry-run 跑满 4 周基线后，作为 B 组实验合入（新币轴证据支持，池内中性）
3. **SuperDD**（`OPT7_SuperDD*.py`）：研究级立线，暂不进组合（与 A 同为趋势族，corr 待算；池内 A 已占趋势预算）
4. FreqAI/Reversion：归档，灭因取证在各自报告

## 账本更新

S1/S3 holdout 各 1 次（12 老币 2024-26）；S2 holdout 2 次（新/老）；S4 holdout 1 次；S5 禁用 2024-26（Router 自身已烧）零接触。11 新币对五族的消耗：S1/S2/S3/S5 各 1 轮（首次）。VolSys 家族（Sleeve A）不受影响。

## 运行事故与修复（本轮）

- S4 agent 死于 10 分钟无输出超时（前台长命令）→ S4b 续命，全部命令后台+轮询，孤儿 zip 解包校验后回收
- S1 与 S5 曾发生 zip 重命名碰撞（并行运行同名 newest-zip 竞争）→ 双方均按内容校验归位，此后 runner 全部改为解包校验式改名
