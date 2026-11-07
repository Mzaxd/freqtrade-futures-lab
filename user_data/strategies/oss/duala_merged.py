# -*- coding: utf-8 -*-
"""DualA — A 内化双尺度引擎(research_lowvol/duala,预注册 2026-11-08)

户主指令:SlowA 既是 A 的变体,把两者内化进一台引擎,做逻辑判断,保留两者优势。
设计决策 8 条冻结于 research_lowvol/duala/pre_reg.md §2(先于任何回测):

  快尺度 = A 原生 3h 事件(resample_hours=3 继承),risk 1%
  慢尺度 = SlowA 的 12h 事件(本文件手动追加 12h 指标列),risk 3%
  入场 = 两尺度信号并集;同向共触发/跨尺度反向冲突 → 慢尺度优先(tag='s12')
  止损/仓位/反手退出 = 按本仓位入场尺度(entry_tag)的 ATR 与裸信号执行
  反手退出仅认本尺度信号(跨尺度意见不互砍);60d 时间止损、P2 熔断全局共享
  回收 = 单一 RECYCLE_MULT 乘总 stake(内化消除两袖双重借用语义)
  单仓语义(freqtrade 原生,同币一笔,不加仓);startup_candle_count=900

与两袖形态(A 袖 + SlowA 袖)的已注册差异:同币重叠期只持一笔 → 敞口低于两袖之和;
跨尺度反向意愿不形成净额对冲。验收门槛 A1-A4 见 pre_reg.md §4。
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from technical.util import resample_to_interval, resampled_merge

from AB_LevGrid import ARL_2x

SLOW_MIN = 12 * 60  # 12h,分钟(freqtrade resample 单位)


class DualA(ARL_2x):
    """主变体 D1:fast 1% @3h + slow 3% @12h。"""

    risk_pct_fast = 0.01
    risk_pct_slow = 0.03
    startup_candle_count = 900  # 12h ATR14=168 根 1h + 30d 门中位数 720 + 余量

    # ------------------------------------------------------------- indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # super():快尺度 3h 列(atr_raw/close_change/gate_atr_med,字节级继承)
        dataframe = super().populate_indicators(dataframe, metadata)

        # 慢尺度 12h 列(与 OPT4_ParamTune.populate_indicators 同构,后缀 _s)
        res = resample_to_interval(dataframe, SLOW_MIN)
        res["atr"] = ta.ATR(res, timeperiod=14)
        res["close_change"] = res["close"].diff()
        dataframe = resampled_merge(dataframe, res, fill_na=True)
        dataframe["atr_raw_s"] = dataframe[f"resample_{SLOW_MIN}_atr"]
        dataframe["close_change_s"] = dataframe[f"resample_{SLOW_MIN}_close_change"]
        dataframe["gate_atr_med_s"] = (
            dataframe["atr_raw_s"]
            .rolling(self.gate_atr_window, min_periods=self.gate_atr_min_periods)
            .median()
        )

        # 两尺度裸信号(退出与入场共用;阈值 = 昨根 ATR × signal_atr_mult,同基类)
        thr_f = dataframe["atr_raw"].shift(1) * self.signal_atr_mult.value
        dataframe["sig_long_f"] = (dataframe["close_change"] > thr_f).fillna(False).astype(int)
        dataframe["sig_short_f"] = (dataframe["close_change"] * -1 > thr_f).fillna(False).astype(int)
        thr_s = dataframe["atr_raw_s"].shift(1) * self.signal_atr_mult.value
        dataframe["sig_long_s"] = (dataframe["close_change_s"] > thr_s).fillna(False).astype(int)
        dataframe["sig_short_s"] = (dataframe["close_change_s"] * -1 > thr_s).fillna(False).astype(int)
        return dataframe

    # ------------------------------------------------------------------ entry
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        gate_f = (dataframe["atr_raw"] >= self.gate_atr_mult * dataframe["gate_atr_med"]).fillna(False)
        gate_s = (dataframe["atr_raw_s"] >= self.gate_atr_mult * dataframe["gate_atr_med_s"]).fillna(False)
        long_f = (dataframe["sig_long_f"] == 1) & gate_f
        short_f = (dataframe["sig_short_f"] == 1) & gate_f
        long_s = (dataframe["sig_long_s"] == 1) & gate_s
        short_s = (dataframe["sig_short_s"] == 1) & gate_s

        has_s = long_s | short_s  # 慢尺度优先:共触发取 s12,跨尺度反向冲突取慢方向
        dataframe["enter_long"] = ((long_s | (long_f & ~has_s))).astype(int)
        dataframe["enter_short"] = ((short_s | (short_f & ~has_s))).astype(int)
        dataframe["enter_tag"] = np.where(has_s, "s12", "f3")
        return dataframe

    # ------------------------------------------------------------------ exits
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 反手退出移到 custom_exit(需要 entry_tag 判尺度);此处显式置空
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        r = super().custom_exit(pair, trade, current_time, current_rate,
                                current_profit, **kwargs)  # 60d 时间止损(继承)
        if r is not None:
            return r
        try:
            df, idx = self._signal_candle(pair, current_time)
            if idx < 0:
                return None
            row = df.iloc[idx]
            slow = (trade.enter_tag or "f3") == "s12"  # Trade 属性名是 enter_tag(回调参数才叫 entry_tag)
            if trade.is_short:
                hit = int(row["sig_long_s" if slow else "sig_long_f"]) == 1
            else:
                hit = int(row["sig_short_s" if slow else "sig_short_f"]) == 1
            if hit:
                return "reverse_s12" if slow else "reverse_f3"
        except Exception:
            return None
        return None

    # ------------------------------------------------- scale-aware stop anchor
    def _anchored_atr(self, trade: Trade) -> float | None:
        # OPT9 缓存机制 + 尺度后缀(键含尺度,防跨尺度污染);Trade 属性名 = enter_tag
        slow = (trade.enter_tag or "f3") == "s12"
        key = f"{self.anchor_cache_key}_{'s12' if slow else 'f3'}"
        cached = trade.get_custom_data(key)
        if cached is not None:
            return float(cached)
        df, idx = self._signal_candle(trade.pair, trade.open_date_utc)
        if idx < 0:
            return None
        col = "atr_raw_s" if slow else "atr_raw"
        atr = float(df.iloc[idx][col])
        if atr != atr or atr <= 0:
            return None
        trade.set_custom_data(key, atr)
        return atr

    # ------------------------------------------------------------------ sizing
    def custom_stake_amount(self, pair: str, current_time: datetime,
                            current_rate: float, proposed_stake: float,
                            min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str,
                            **kwargs) -> float:
        # OPT9 逐字节语义 + 尺度参数化(列/risk)+ OPT9_Recycle 回收尾单乘数
        def conservative() -> float:
            s = proposed_stake * 0.5
            s = min(s, max_stake) if max_stake else s
            if min_stake is not None:
                s = max(s, min_stake)
            return s

        try:
            df, idx = self._signal_candle(pair, current_time)
            if idx < 0:
                return conservative()
            slow = entry_tag == "s12"
            row = df.iloc[idx]
            atr = float(row["atr_raw_s" if slow else "atr_raw"])
            close = float(row["close"])
            if atr != atr or atr <= 0 or close != close or close <= 0:
                return conservative()
            stop_pct = max(float(self.stop_atr_mult.value) * atr / close, self.stop_pct_floor)
            equity = self.wallets.get_total_stake_amount()
            risk = (self.risk_pct_slow if slow else self.risk_pct_fast) \
                * self._risk_fraction(side, current_time)
            notional = equity * risk / stop_pct
            stake = notional / max(leverage, 1.0)
            stake = min(stake, equity * self.margin_cap, max_stake)
            if min_stake is not None:
                stake = max(stake, min_stake)
        except Exception:
            return conservative()

        # 回收尾(= OPT9_Recycle 语义:门开时总 stake × RECYCLE_MULT,单一乘数)
        if float(self.RECYCLE_MULT) != 1.0:
            try:
                if self._recycle_on(current_time):
                    stake = stake * float(self.RECYCLE_MULT)
                    if max_stake:
                        stake = min(stake, max_stake)
            except Exception:
                pass  # 回收信号失败 → 原额放行(同 OPT9_Recycle 降级语义)
        return stake


class DualA_vt60f1(DualA):
    """D2:D1 + vol-target overlay(risk×clamp(60.6/RV30,1,2));钩子实现与
    lvg_A_riskvol.LVG_A_VolTarget 逐字同构(复制而非多继承,MRO 无歧义)。"""

    VT_TARGET = 60.6
    VT_M_LO = 1.0
    VT_M_HI = 2.0
    _vt_cache: tuple | None = None

    def _rv30_pct(self, current_time: datetime) -> float | None:
        if self.dp is None:
            return None
        df = self.dp.get_pair_dataframe(self.RECYCLE_REF, self.timeframe)
        if df is None or len(df) == 0:
            return None
        ts = pd.Timestamp(current_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        idx = int(df["date"].searchsorted(ts.floor("ms"))) - 1
        if idx < 24 * 35:
            return None
        key = (len(df), idx)
        if self._vt_cache is not None and self._vt_cache[0] == key:
            return self._vt_cache[1]
        closes = df["close"].iloc[: idx + 1]
        closes.index = pd.DatetimeIndex(df["date"].iloc[: idx + 1])
        daily = closes.resample("1D").last()
        while len(daily) and (daily.index[-1] + pd.Timedelta(days=1)) > ts:
            daily = daily.iloc[:-1]
        rv = None
        if len(daily) >= 31:
            rets = (daily / daily.shift(1)).dropna().iloc[-30:]
            rets = rets[rets > 0]
            if len(rets) == 30:
                lr = rets.map(lambda x: math.log(x))
                mu = sum(lr) / 30.0
                var = sum((x - mu) ** 2 for x in lr) / 29.0
                rv = math.sqrt(var) * math.sqrt(365.0) * 100.0
        self._vt_cache = (key, rv)
        return rv

    def _risk_fraction(self, side: str, current_time: datetime) -> float:
        rv = self._rv30_pct(current_time)
        if rv is None or rv <= 0:
            return 1.0
        m = float(self.VT_TARGET) / rv
        return min(max(m, float(self.VT_M_LO)), float(self.VT_M_HI))


class DualA_F1S2(DualA):
    """D3 稳健性臂:慢尺度降为 risk 2%(r2 零截断档)。"""

    risk_pct_slow = 0.02


# ── v2:慢尺度抢占语义(research_lowvol/duala/pre_reg_v2.md,2026-11-08)────
class DualA2(DualA):
    """D4:v1 诊断(快引擎 8x 事件密度饿死慢引擎,30/129 吞吐)后的唯一语义变更:
    慢尺度门控入场信号(任一方向)出现时,f3 仓位让位(preempt_s12),s12 接管该币槽位;
    其余语义逐字继承 DualA。验收 B1-B4 见 pre_reg_v2.md §4。"""

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        r = super().custom_exit(pair, trade, current_time, current_rate,
                                current_profit, **kwargs)  # 时间止损 + 本尺度反手(继承)
        if r is not None:
            return r
        if (trade.enter_tag or "f3") != "f3":
            return None  # s12 永不被抢占
        try:
            df, idx = self._signal_candle(pair, current_time)
            if idx < 0:
                return None
            row = df.iloc[idx]
            med = row["gate_atr_med_s"]
            gate_s = (med == med) and float(row["atr_raw_s"]) >= self.gate_atr_mult * float(med)
            if gate_s and (int(row["sig_long_s"]) == 1 or int(row["sig_short_s"]) == 1):
                return "preempt_s12"
        except Exception:
            return None
        return None


class DualA2_vt60f1(DualA2, DualA_vt60f1):
    """D5:D4 + vt overlay(菱形继承:custom_exit 取 DualA2 抢占版,
    _rv30_pct/_risk_fraction 取 DualA_vt60f1,其余共享 DualA 基座)。"""
