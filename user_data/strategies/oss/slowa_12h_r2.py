# -*- coding: utf-8 -*-
"""SlowA_12h_r2 — LV1 放大变体 #1 (research_lowvol/lv1/pre_reg.md, 2026-11-07)

唯一改动: risk_pct 0.01 -> 0.02 (A 家族唯一真拨盘, 账本 §3.6: notional =
equity x risk / stop_pct, 杠杆只是保证金、PnL 中性, risk 等比缩放收益与回撤)。
其余字节级继承 SlowA_12h (12h 事件尺度 + OPT9_Recycle 全部冻结结构)。
预注册点, 不参与任何 hyperopt; 结果无论好坏全披露。
"""
from slowa_12h import SlowA_12h


class SlowA_12h_r2(SlowA_12h):
    risk_pct = 0.02
