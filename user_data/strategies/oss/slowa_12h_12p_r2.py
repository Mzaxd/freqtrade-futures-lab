# -*- coding: utf-8 -*-
"""SlowA_12h_12p_r2 — LV1 放大变体 #4 (research_lowvol/lv1/pre_reg.md, 2026-11-07)

改动: 12 币宇宙 (同 slowa_12h_12p) + risk_pct 0.01 -> 0.02。
分散 x 拨盘的交叉点。预注册点, 不参与 hyperopt; 结果全披露。
"""
from slowa_12h import SlowA_12h


class SlowA_12h_12p_r2(SlowA_12h):
    risk_pct = 0.02
