# -*- coding: utf-8 -*-
"""XS agent 的 Sleeve A 参照：原封不动的 OPT4_VolatilitySystem（类名加 XS_ 前缀保证 zip 可区分）。
仅用于重跑 2021-2023 提取日/月收益做组合相关性，不修改任何逻辑。
OPT4_VolatilitySystem.py 为只读复制品（沙盒内可导入）。"""
from OPT4_VolatilitySystem import OPT4_VolatilitySystem


class XS_OPT4Ref(OPT4_VolatilitySystem):
    pass
