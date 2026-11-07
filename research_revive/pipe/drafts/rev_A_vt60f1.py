"""rev_A_vt60f1 — 草案,未部署(research_revive/pipe/drafts/)。

方案3 影子栈 A 袖可部署子类:LVG_A_vt60f1(冻结研究文件
user_data/strategies/oss/lvg_A_riskvol.py,不许编辑)+ 两处部署层补丁,
信号/钩子语义零改动:

1. startup_candle_count 200 -> 2600(108 天 1h):
   live/dry-run 下 dp.get_pair_dataframe 返回 live 蜡烛缓存,初始抓取量 =
   startup_candle_count。继承链需要:
     - OPT9_Recycle 回收层 SMA100(>= 100 闭合日 = 2400h)
     - LVG_A_VolTarget RV30(>= 31 闭合日 = 744h)
   startup=200(8.3 天)会让进程启动后前 ~100 天 回收层静默 OFF + m=1(双重中性,
   偏离 ★ 回测语义)。2600 在 Binance 单次 1500 根×5 批限额内。
   回测路径不受影响(数据加载窗口足够),P1.3 以 trade-diff=0 验证。

2. 每小时一条可 grep 状态行(影子期 "vt 乘数分布 vs 回测" gate 的数据源):
   REV-VT status rv30=60.1 m=1.008 floor=1.0 hi=2.0

执行时复制到 user_data/strategies/oss/rev_A_vt60f1.py(新文件,前缀 rev_)。
"""
from __future__ import annotations

import logging
from datetime import datetime

from lvg_A_riskvol import LVG_A_vt60f1

logger = logging.getLogger(__name__)


class Rev_A_vt60f1(LVG_A_vt60f1):
    # live 预热:108 天 1h,使回收 SMA100 与 RV30 从第一根起可算(见 docstring)
    startup_candle_count = 2600

    # 状态日志节流键(小时级;与 _vt_cache 独立,不影响计算)
    _rev_log_key: str | None = None

    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        m = super()._risk_fraction(side, current_time)
        key = current_time.strftime("%Y-%m-%dT%H")
        if Rev_A_vt60f1._rev_log_key != key:
            rv = self._rv30_pct(current_time)
            logger.info(
                "REV-VT status rv30=%s m=%.3f floor=%.1f hi=%.1f",
                "NA" if rv is None else f"{rv:.1f}",
                m, float(self.VT_M_LO), float(self.VT_M_HI),
            )
            Rev_A_vt60f1._rev_log_key = key
        return m
