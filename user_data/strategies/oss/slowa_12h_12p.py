# -*- coding: utf-8 -*-
"""SlowA_12h_12p — LV1 放大变体 #3 (research_lowvol/lv1/pre_reg.md, 2026-11-07)

唯一改动: 交易宇宙 3 币 -> lab 冻结 12 币白名单 (BTC/ETH/SOL/BNB/XRP/ADA/DOGE/
AVAX/LINK/DOT/LTC/UNI, 经 CLI -p 传入; 与 OPT7_config_12p / 12币等权基线同源)。
策略代码零改动 (risk_pct 仍 0.01); MOT=12 由 CLI 传入 = 并发不另设限,
仓位纪律完全交给 A 家族 risk sizing + margin_cap 0.35。
已知继承语义 (披露): P2 熔断是全局同向计数, 12 币下触发频率高于 3 币 ——
这是"同结构宽宇宙"直译的一部分, 不做任何门控修改。预注册点, 全披露。
"""
from slowa_12h import SlowA_12h


class SlowA_12h_12p(SlowA_12h):
    pass  # risk_pct = 0.01 (继承); 宇宙改动在 config/CLI 层
