"""OPT1_MomRegime15mFast — Phase-1 Agent-D optimization of NC_MomRegime15mFast.

Base strategy: NC_MomRegime15mFast.py (Agent C adaptation of nateemma/strategies
Basket/MomentumRegimeBasket15m.py + MomentumRegimeBasket15mFast.py), itself
documented there.  This file is a signal-identical copy EXCEPT for the funding
gate described below.

OPT1 changes vs NC_MomRegime15mFast (the ONLY logic deltas):
  1. populate_indicators calls opt_common.attach_funding() to add a causal
     `funding_rate` column (settled rate one full settlement old; NaN when the
     pair has no funding feather — LINK/DOT/LTC/UNI in this lab).
  2. Long entries (populate_entry_trend) additionally require
     opt_common.funding_gate_long(df, funding_max): the latest settled funding
     rate must be <= funding_max (NaN passes).
  3. adjust_trade_position: the ACCUMULATION branch (adding toward the
     equal-weight target pv/TOP_N) is blocked while the latest candle's settled
     funding_rate > funding_max (NaN passes).  The MAX_POSITION_WEIGHT trim
     branch and all exit/liquidity-unwind logic are UNTOUCHED.

funding_max = 0.0005 (0.05% / 8h ~= 66% annualized) is a FIXED ENGINEERING
THRESHOLD — deliberately not hyperopted: 15m x 12-pair backtests are too slow
to support a hyperopt search budget in this phase.

Universe for this variant: 12-coin majors (BTC ETH SOL BNB XRP ADA DOGE AVAX
LINK DOT LTC UNI), where the cross-sectional top-3 ranking is actually
discriminative (unlike the 3-coin degenerate case where rank<=TOP_N is always
true for all whitelisted pairs).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

import opt_common   # same-dir helper: causal funding attach + gate

# lab futures daily feathers (freqtrade download-data naming)
FEATHER_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "binance" / "futures"


class OPT1_MomRegime15mFast(IStrategy):
    timeframe = "15m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 200   # 15m frames only need current price; history comes from daily feathers
    stoploss = -0.99          # rotation is via signals, not stops
    minimal_roi = {"0": 100}  # ROI off
    trailing_stop = False
    use_exit_signal = True
    position_adjustment_enable = True   # REQUIRED — accumulate fills toward target

    MOM_LOOKBACK_DAYS = 14   # 90 -> 14: rotate the basket on 2-week momentum (Fast variant)
    TOP_N = 3                # == config max_open_trades
    REGIME_SMA = 100         # BTC trend window, in DAILY candles
    REGIME_REF = "BTC/USDT:USDT"

    REGIME_TOLERANCE = 0.0
    REBALANCE_HOURLY = True  # only change top-N membership on the hour

    EXIT_RANK_N = 9

    TREND_FILTER_ENABLE = True
    PER_COIN_SMA = 50        # a held coin must be above its own DAILY SMA(this)

    MAX_POSITION_WEIGHT = 0.45

    EXIT_LIQUIDITY_CAP = True

    MIN_QUOTE_VOLUME = 1000
    QUOTE_VOLUME_HEADROOM_MULT = 10.0   # fill <= 1/10 of a candle's quote volume

    FILL_VOLUME_LAG = 0

    # OPT1: fixed engineering threshold (0.05%/8h ~ 66% annualized); NOT hyperopted.
    funding_max = 0.0005

    _xs = None       # cached membership matrix (bool DataFrame, per pair)
    _xs_key = None   # cache key: (latest candle date, whitelist, *_xs_params())

    def _daily_closes(self, pairs) -> DataFrame:
        """Full-history daily close panel, read straight from the futures feathers."""
        out = {}
        for p in pairs:
            base = p.split("/")[0]
            f = FEATHER_DIR / f"{base}_USDT_USDT-1d-futures.feather"
            if f.exists():
                d = pd.read_feather(f)
                d["date"] = pd.to_datetime(d["date"], utc=True)
                out[p] = d.set_index("date")["close"]
        return pd.DataFrame(out).sort_index()

    def _xs_params(self) -> tuple:
        return (
            int(self.MOM_LOOKBACK_DAYS),
            int(self.TOP_N),
            int(self.REGIME_SMA),
            float(self.REGIME_TOLERANCE),
            str(self.REGIME_REF),
            bool(self.REBALANCE_HOURLY),
            bool(self.TREND_FILTER_ENABLE),
            int(self.PER_COIN_SMA),
            None if self.EXIT_RANK_N is None else int(self.EXIT_RANK_N),
        )

    def _compute_xs(self) -> DataFrame:
        """Causal top-N membership AND-ed with BTC daily risk-on, per 15m date."""
        wl = tuple(sorted(self.dp.current_whitelist()))
        ref = self.dp.get_pair_dataframe(self.REGIME_REF, self.timeframe)
        asof = ref["date"].iloc[-1] if ref is not None and len(ref) else None
        key = (asof, wl) + self._xs_params()
        if self._xs is not None and self._xs_key == key:
            return self._xs

        # --- daily inputs (full history from disk), lagged 1 day to stay causal ---
        Pd = self._daily_closes(wl)
        known = Pd.shift(1)                                        # yesterday's close, known intraday
        ref90 = known.shift(self.MOM_LOOKBACK_DAYS)               # daily close ~lb days ago
        btc_d = known.get(self.REGIME_REF)
        if btc_d is not None:
            ron_d = (btc_d > btc_d.rolling(self.REGIME_SMA).mean()
                     * (1.0 - self.REGIME_TOLERANCE))
        else:
            ron_d = pd.Series(True, index=Pd.index)

        # --- current 15m close panel (freqtrade-loaded) ---
        closes = {}
        for p in wl:
            df = self.dp.get_pair_dataframe(p, self.timeframe)
            if df is not None and len(df):
                s = df.copy(); s["date"] = pd.to_datetime(s["date"], utc=True)
                closes[p] = s.set_index("date")["close"]
        P15 = pd.DataFrame(closes).sort_index()

        # map daily inputs onto the 15m index (ffill = as-of the latest known day)
        ref90_15 = ref90.reindex(columns=P15.columns).reindex(P15.index, method="ffill")
        risk_on = ron_d.reindex(P15.index, method="ffill").fillna(False)
        mom = P15 / ref90_15 - 1                                  # intraday-responsive lb-day momentum
        rank = mom.rank(axis=1, ascending=False, method="first")

        # Hard gates (NO hysteresis on these -- they are the risk controls)
        gate = pd.DataFrame(True, index=P15.index, columns=P15.columns)
        if self.TREND_FILTER_ENABLE:                              # drop coins below their own trend
            trend_ok = (known > known.rolling(self.PER_COIN_SMA).mean())
            trend_ok_15 = trend_ok.reindex(columns=P15.columns).reindex(P15.index, method="ffill").fillna(False)
            gate = gate & trend_ok_15
        gate = gate.apply(lambda col: col & risk_on)

        exit_n = self.TOP_N if self.EXIT_RANK_N is None else self.EXIT_RANK_N
        enter_ok = (rank <= self.TOP_N) & gate
        stay_ok = (rank <= exit_n) & gate

        # Decision points: hourly if rebalancing hourly, else every candle.
        idx = P15.index[P15.index.minute == 0] if self.REBALANCE_HOURLY else P15.index
        held = self._hysteresis_membership(rank.loc[idx], enter_ok.loc[idx], stay_ok.loc[idx])
        want = held.reindex(P15.index, method="ffill").fillna(False).astype(bool)
        self._xs = want
        self._xs_key = key
        return self._xs

    def _hysteresis_membership(self, rank: DataFrame, enter_ok: DataFrame,
                               stay_ok: DataFrame) -> DataFrame:
        """Slot-based forward scan over the decision index. Causal by construction."""
        r = rank.to_numpy()
        e = enter_ok.to_numpy()
        st = stay_ok.to_numpy()
        n_rows, n_cols = e.shape
        out = np.zeros((n_rows, n_cols), dtype=bool)
        held = np.zeros(n_cols, dtype=bool)
        for i in range(n_rows):
            held &= st[i]                                  # vacate slots that failed
            free = self.TOP_N - int(held.sum())
            if free > 0:
                cand = np.flatnonzero(e[i] & ~held)
                if cand.size:
                    cand = cand[np.argsort(r[i][cand], kind="stable")]
                    held[cand[:free]] = True
            out[i] = held
        return DataFrame(out, index=enter_ok.index, columns=enter_ok.columns)

    def _hold_flag(self, pair: str, dates: pd.Series) -> pd.Series:
        want = self._compute_xs()
        w = want[pair] if pair in want.columns else pd.Series(False, index=want.index)
        left = pd.DataFrame({"date": pd.to_datetime(dates, utc=True)})
        m = pd.merge_asof(left.sort_values("date"),
                          w.rename("hold").reset_index().rename(columns={"index": "date"}).sort_values("date"),
                          on="date", direction="backward")
        return m["hold"].fillna(False).astype(bool)

    def _portfolio_value(self) -> float:
        """Mark-to-market total = free cash + open position values."""
        stake_ccy = self.config["stake_currency"]
        pv = self.wallets.get_free(stake_ccy)
        for ot in Trade.get_trades_proxy(is_open=True):
            df, _ = self.dp.get_analyzed_dataframe(ot.pair, self.timeframe)
            price = df["close"].iloc[-1] if df is not None and len(df) else ot.open_rate
            pv += ot.amount * price
        return pv

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["hold"] = self._hold_flag(metadata["pair"], dataframe["date"]).values
        dataframe = opt_common.attach_funding(dataframe, metadata["pair"])
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["hold"]
            & (dataframe["volume"] > 0)
            & opt_common.funding_gate_long(dataframe, self.funding_max),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[~dataframe["hold"], "exit_long"] = 1   # exit when out of top-N or risk-off
        return dataframe

    def _quote_volume(self, df) -> float:
        i = -1 - self.FILL_VOLUME_LAG
        if df is None or len(df) < abs(i):
            return 0.0
        bar = df.iloc[i].squeeze()
        return float(bar["volume"]) * float(bar["close"])

    # --- liquidity-aware sizing: cap the INITIAL fill to the equal-weight target
    #     AND to <=10% of the candle's quote volume ---
    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        if self.dp.runmode.value in ("plot", "other"):
            return proposed_stake
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        target = self._portfolio_value() / self.TOP_N
        stake = min(proposed_stake, target, fillable, max_stake)
        if min_stake and stake < min_stake:
            return 0.0
        return max(stake, 0.0)

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        if self.dp.runmode.value in ("plot", "other"):
            return True
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        return self._quote_volume(df) >= self.MIN_QUOTE_VOLUME   # reject dust

    def confirm_trade_exit(self, pair, trade, order_type, amount, rate, time_in_force,
                           exit_reason, current_time, **kwargs):
        """Refuse a full exit the candle cannot absorb; adjust_trade_position then
        shaves the position down over subsequent candles until it can."""
        if not self.EXIT_LIQUIDITY_CAP or self.dp.runmode.value in ("plot", "other"):
            return True
        if exit_reason in ("force_exit", "stop_loss", "liquidation"):
            return True                      # never block a forced exit
        df, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        sellable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        return (amount * rate) <= sellable

    # --- ACCUMULATION: add toward the equal-weight target each candle, capped to
    #     <=10% of the candle's quote volume, while the coin is still in the basket ---
    def adjust_trade_position(self, trade, current_time, current_rate, current_profit,
                              min_stake, max_stake, current_entry_rate, current_exit_rate,
                              current_entry_profit, current_exit_profit, **kwargs):
        if self.dp.runmode.value in ("plot", "other"):
            return None
        df, _ = self.dp.get_analyzed_dataframe(pair=trade.pair, timeframe=self.timeframe)
        if df is None or len(df) == 0:
            return None
        last = df.iloc[-1].squeeze()
        pv = self._portfolio_value()
        current_value = trade.amount * current_rate
        # max-position-weight cap: trim a runaway winner first (banks profit into cash)
        if self.MAX_POSITION_WEIGHT and pv > 0 and current_value > self.MAX_POSITION_WEIGHT * pv:
            trim = self.MAX_POSITION_WEIGHT * pv - current_value   # negative => reduce
            if not min_stake or abs(trim) >= min_stake:
                return trim
        if not bool(last["hold"]):
            if not self.EXIT_LIQUIDITY_CAP:
                return None   # leaving the basket -> full exit handled by the exit signal
            # Liquidity-capped unwind: release only what this candle can absorb.
            sellable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
            if sellable <= 0 or sellable >= current_value:
                return None
            reduce = -min(sellable, current_value)
            if min_stake and abs(reduce) < min_stake:
                return None
            return reduce
        # OPT1 funding gate on ACCUMULATION adds: skip adding while the latest
        # settled funding rate is above the threshold (NaN = no data -> allow).
        # Trim/exit paths above are deliberately NOT gated.
        fr = last.get("funding_rate")
        if pd.notna(fr) and float(fr) > self.funding_max:
            return None
        target = pv / self.TOP_N
        if current_value >= target * 0.98:
            return None   # already at target weight
        fillable = self._quote_volume(df) / self.QUOTE_VOLUME_HEADROOM_MULT
        add = min(target - current_value, fillable, max_stake)
        if add <= 0 or (min_stake and add < min_stake):
            return None
        return add
