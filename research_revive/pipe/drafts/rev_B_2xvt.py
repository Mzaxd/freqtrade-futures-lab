"""rev_B_2xvt — 草案,未部署(research_revive/pipe/drafts/)。

方案3 影子栈 B 袖可部署子类:LVG_B_2xvt(冻结研究文件
user_data/strategies/oss/lvg_B_lev.py,不许编辑)+ 修复其唯一 live/dry-run 缺陷:

  LVG_B_Lev._btc_daily_closes 是一次性类级静态缓存(进程启动读一次 BTC 1d feather
  后永不重读)。长跑 dry-run/实盘里,即使 scheduler 每日刷新 feather,运行中的
  RV30(与杠杆乘数)仍会静默冻结在进程启动时的数据末端 —— 与 opt_common 的
  mtime 感知 funding 缓存(commit 7ea932c)背道而驰。

本子类 override _btc_daily_closes 为 mtime 感知缓存(opt_common 惯例):
feather 的 st_mtime_ns 变化即重读,每日 00:10Z 刷新后免重启生效;
数据陈旧 >36h 打告警行(对应 kill 规则 K6:>48h 停 B)。
另加入场时状态行(影子期 "lev 分布 vs 回测" gate 的数据源):
  REV-LEV status pair=BTC/USDT:USDT rv30=55.2 lev=2.19 lo=1.0 hi=2.5

信号语义逐字节不变(leverage() 公式完全走父类)。P1.4 以 trade-diff=0 验证。
执行时复制到 user_data/strategies/oss/rev_B_2xvt.py(新文件,前缀 rev_)。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from lvg_B_lev import LVG_B_2xvt

logger = logging.getLogger(__name__)

_FEATHER = (Path(__file__).resolve().parents[2] / "data" / "binance" / "futures"
            / "BTC_USDT_USDT-1d-futures.feather")
_STALE_WARN_S = 36 * 3600   # K6: 陈旧告警阈值(监控层 >48h 再停机)


class Rev_B_2xvt(LVG_B_2xvt):
    # mtime 感知缓存:(st_mtime_ns, series);mtime 变化即重读
    _rev_cache: tuple | None = None

    def _btc_daily_closes(self) -> pd.Series | None:
        try:
            mtime = _FEATHER.stat().st_mtime_ns
            age = time.time() - _FEATHER.stat().st_mtime
        except OSError:
            mtime, age = None, None
        if mtime is not None and Rev_B_2xvt._rev_cache is not None \
                and Rev_B_2xvt._rev_cache[0] == mtime:
            return Rev_B_2xvt._rev_cache[1]
        if not _FEATHER.exists():
            return None
        d = pd.read_feather(_FEATHER)
        s = (d.set_index(pd.DatetimeIndex(pd.to_datetime(d["date"], utc=True)))["close"]
             .sort_index())
        Rev_B_2xvt._rev_cache = (mtime, s)
        if age is not None and age > _STALE_WARN_S:
            logger.warning("REV-LEV feather stale %.1fh (>%.0fh) — RV30 用旧数据,查数据刷新",
                           age / 3600.0, _STALE_WARN_S / 3600.0)
        return s

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        lev = super().leverage(pair, current_time, current_rate, proposed_leverage,
                               max_leverage, entry_tag, side, **kwargs)
        rv = self._rv30_pct(current_time)
        logger.info("REV-LEV status pair=%s rv30=%s lev=%.2f lo=%.1f hi=%.2f",
                    pair, "NA" if rv is None else f"{rv:.1f}",
                    lev, float(self.LVG_LO), float(self.LVG_HI))
        return lev
