# -*- coding: utf-8 -*-
"""SlowA_12h — 慢A袖预注册候选 (research_revive/slowa, 2026-11-07)

结构变体: 冻结 A (ARL_2x = OPT9_Recycle MULT=1.21 + lev2) 的唯一改动是
事件尺度 — resample_hours 3 -> 12 (3h 事件 -> 12h 事件)。其余全部字节级
继承: 双ATR (signal=stop=2.0 x ATR14 on resampled bars), atr08 门 (30天窗,
窗口单位是 1h 行, 不随 resample 改变), 60d 时间止损, P2 全局同向簇熔断,
recycle x1.21, 1%-risk sizing (notional = equity x risk/stop_pct), lev 2x。

论证 (结构变体 vs 调参): resample_hours 改变 close_change/ATR 的事件集本身
(哪些 K 线时刻产生入场信号), 不是在固定事件集上调既有参数 — 已证伪的调优
雷区 (rank IC -0.156) 是后者。预注册于 research_revive/slowa/report.md;
S12h 点位选择的多重检验代价在那里诚实披露。

只跑这一个变体 (单变体单次); 不进入任何 hyperopt。
"""
from freqtrade.strategy import IntParameter

from OPT9_Recycle import OPT9_Recycle


class SlowA_12h(OPT9_Recycle):
    RECYCLE_MULT = 1.21          # 同 ARL_2x
    leverage_fixed = 2.0         # 同 ARL_2x
    # 唯一改动: 事件尺度 3h -> 12h (固定值, 不参与优化)
    resample_hours = IntParameter(12, 12, default=12, space="buy", optimize=False)
