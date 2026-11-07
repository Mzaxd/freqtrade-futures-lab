# -*- coding: utf-8 -*-
"""SlowA_12h_r3 — LV1 放大变体 #2 (research_lowvol/lv1/pre_reg.md, 2026-11-07)

唯一改动: risk_pct 0.01 -> 0.03。其余字节级继承 SlowA_12h。
用途: risk 1->2->3 拐点形状(线性 or 超线性; margin_cap 0.35 / 复利 /
强平交互的首个可能触点)。预注册点, 不参与 hyperopt; 结果全披露。
"""
from slowa_12h import SlowA_12h


class SlowA_12h_r3(SlowA_12h):
    risk_pct = 0.03
