# -*- coding: utf-8 -*-
"""ESB_B_2xvt — B_vt 的 ESB 宇宙(ETH/SOL/BNB)注入子类(research_lowvol/esb,2026-11-08)

唯一改动:复刻 AB_RaySleeves.AB_Ray_B 的注入——BTC 不在白名单时,把 BTC 日线
注入 regime 面板(panel-only,BTC 不可交易、其 membership 列被入场/出场忽略),
保持 regime 门与冻结语义字节等价。LVG_B_2xvt 的 RV30 读文件级 BTC 日线 feather,
与白名单无关。其余逐字继承 LVG_B_2xvt(mpw45 / tol -0.03 / abs funding 门 /
TOP_N=3 / MOM14 / SMA50 / lev=clamp(2×60.6/RV30,1,2.5))。
"""
from lvg_B_lev import LVG_B_2xvt


class ESB_B_2xvt(LVG_B_2xvt):
    def _daily_closes(self, pairs) -> "object":
        # BTC 只进面板不进白名单——见 AB_RaySleeves.AB_Ray_B 的同型注入与论证
        return super()._daily_closes(tuple(sorted(set(pairs) | {self.REGIME_REF})))
