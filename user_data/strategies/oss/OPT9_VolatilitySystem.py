"""OPT9_VolatilitySystem — trade-forensic optimization release (2026-11-01).

Built from the 8-agent per-trade forensic program over the frozen OPT4 IS
benchmark (433 trades, 12 coins, 2021-23, +1495.8% / DD 15.92% / PF 1.97).
Every window agent independently converged on the same three structural
leaks; all three fixes here live on the EXIT / RISK-GOVERNANCE side.
Entry signals, initial stop geometry, 1%-risk sizing, 2x leverage, 1h/3h
timeframes: unchanged from frozen OPT4.

---------------------------------------------------------------------
BUG FIX vs parent OPT8 (found 2026-11-01 while reproducing the baseline):
OPT8's custom_stoploss re-looks-up the entry candle every call. In
freqtrade >=2024.x backtest (and any live window where the entry candle
aged out), get_analyzed_dataframe returns only the last 1000 candles, so
for trades held > ~1000 x 1h (~42 days) _signal_candle returns -1 and the
code falls back to fallback_stop_ratio = -0.10 as a RAW ratio — which
adjust_stop_loss interprets RELATIVE TO CURRENT PRICE: a 5% trailing stop
that ratchets with every new high. It only ever fires on long-held trades,
i.e. exactly the trend monsters: in the 12p IS replay it cut +1464% to
+1171% and truncated 15 big winners. Fix here (two parts):
  1. anchor ATR is looked up ONCE (entry candle is guaranteed fresh at the
     first call) and cached on the trade via set_custom_data;
  2. the fallback is now a static stop anchored at the ENTRY price via
     stoploss_from_open — the originally intended semantics.
See OPT8b_VolatilitySystem.py for the standalone run-3 hotfix candidate.
---------------------------------------------------------------------

P1 be_floor — profit-path management (7/8 agents' top finding)
   Leak: ~77-109 IS trades reached >= +1x-stop-distance favorable
   excursion, then gave ALL of it back and stopped at full -1R
   (2022H2: 14 trades / -8.7k; 2023H2: 16 / -15.4k). The entry-anchored
   stop never ratchets. Winners additionally pay a ~0.53*MFE giveback
   tax to the reverse-signal exit (corr 0.957).
   Fix: once price travels >= be_arm_r x stop_dist in our favor, the
   stop ratchets to entry +/- be_buffer_atr x ATR_entry (small locked
   profit, fee-aware buffer). Before arming: byte-identical to OPT4.
   Fat-tail safety: floor only tightens (framework ratchets), never
   widens; 2023H1 forensics showed the arming threshold sits in an
   empty zone (all winners MFE/stop_dist >= 2.3, immediate-losers
   <= 0.75), and 1.5R was chosen inside that gap.

P2 cluster_circuit — directional stop-cluster circuit breaker
   Leak: maxDD anatomy = "one-sided stop cluster -> same-direction
   re-entry -> next cluster" chains (2023: 7-cluster chain = the
   15.92% maxDD). After one-sided clusters, SAME-direction entries
   within 72h lost -2,516 across 12 trades while COUNTER-direction
   entries made +53,758 across 31 (first-order replay: DD 15.92 ->
   13.22%, profit +3.7%).
   Fix: >= cluster_stop_count same-direction stop LOSSES within
   cluster_window_h -> decline NEW same-direction entries for
   circuit_hours from the most recent such stop. Existing positions
   and counter-direction entries untouched; auto-expires.
   Not on the falsified list: phase4 cooldown was per-pair /
   direction-blind / permanent; phase6 CC1a/b were global caps whose
   blocked set was net-POSITIVE (rejected winners). Here the blocked
   set is net-negative and the trigger is our own stop events.

P3 time_stop exemption — stop cutting only winners
   All 4 time_stop_60d exits in the benchmark were deep winners
   (+51% .. +391%); ZERO losers ever survived 40 days — the
   anti-zombie blade never cut a zombie, only truncated the right
   tail (3/3 in 2022H1 forced out far from their peaks).
   Fix: the 60d time stop only fires when profit_ratio <
   time_stop_exempt_profit; deep winners keep riding until the
   reverse signal.

Verification protocol (pre-registered before the first OPT9 run):
  baseline reproduce -> all-off sanity (== baseline) -> ablations
  (A/B/C singles) -> combined -> guards: maxDD <= baseline+0.5pp,
  six half-year slices all positive, top-20 winner profit >= 95% of
  baseline (fat tail intact).
"""
from datetime import datetime, timedelta

from freqtrade.persistence import Trade
from freqtrade.strategy import stoploss_from_absolute, stoploss_from_open

from OPT8_VolatilitySystem import OPT8_VolatilitySystem


class OPT9_VolatilitySystem(OPT8_VolatilitySystem):
    # --- bug-fix knobs (see module docstring) ---
    anchor_cache_key = "opt9_atr_entry"

    # --- P1: profit floor — FALSIFIED 2026-11-01 at two pre-registered
    # points (arm 1.5R and 2.5R, buffer 0.5 ATR): any floor armed on price
    # excursion catches winners mid-path (their intermediate peaks precede
    # the final run and deep retests are how this system's fat tail is
    # bought). 1.5R: +530% / DD 33.2; 2.5R: +930% / DD 29.1 vs baseline
    # +1464% / 15.95%. Kept OFF and documented; do not re-test without a
    # structurally different arming signal. ---
    be_floor = False
    be_arm_r = 1.5          # arm when favorable excursion >= 1.5 x stop distance
    be_buffer_atr = 0.5     # floor at entry +/- 0.5 x ATR_entry (fee cushion)

    # --- P2: one-sided stop-cluster circuit breaker — THE surviving fix
    # (IS 12p: DD 15.95 -> 10.10%, PF 1.97 -> 2.03, profit -3.2%, all
    # guards pass; see opt9 program report) ---
    cluster_circuit = True
    cluster_stop_count = 2  # >= N same-direction stop losses ...
    cluster_window_h = 24   # ... within this many hours
    circuit_hours = 48      # ... block same-direction NEW entries this long

    # --- P3: time-stop profit exemption — FALSIFIED 2026-11-01 (-2.4%
    # profit: the 60d-cut winners did WORSE riding into their reversals;
    # 0 losers ever reached 40d so the exemption only extends winners). ---
    time_stop_exempt = False
    time_stop_exempt_profit = 0.20  # ratio incl. leverage (2x => +10% price)

    # ------------------------------------------------------------- anchor ATR
    def _anchored_atr(self, trade: Trade) -> float | None:
        """Entry-signal ATR, looked up once and cached on the trade.

        Survives the entry candle aging out of the (sliding) analyzed
        dataframe window — the OPT8 latent bug.
        """
        cached = trade.get_custom_data(self.anchor_cache_key)
        if cached is not None:
            return float(cached)
        df, idx = self._signal_candle(trade.pair, trade.open_date_utc)
        if idx < 0:
            return None
        atr = float(df.iloc[idx]["atr_raw"])
        if atr != atr or atr <= 0:  # NaN guard without pandas import
            return None
        trade.set_custom_data(self.anchor_cache_key, atr)
        return atr

    # ------------------------------------------------------------------ P1+P0
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        lev = trade.leverage or 1.0
        atr_entry = self._anchored_atr(trade)
        if atr_entry is None:
            # static tight stop anchored at the ENTRY price (NOT current price)
            return stoploss_from_open(self.fallback_stop_ratio, current_rate,
                                      is_short=trade.is_short, leverage=lev)
        stop_dist = float(self.stop_atr_mult.value) * atr_entry

        if trade.is_short:
            stop_price = trade.open_rate + stop_dist
            if self.be_floor and trade.min_rate:
                if trade.open_rate - trade.min_rate >= self.be_arm_r * stop_dist:
                    stop_price = min(stop_price, trade.open_rate - self.be_buffer_atr * atr_entry)
            return stoploss_from_absolute(stop_price, current_rate, is_short=True, leverage=lev)

        stop_price = trade.open_rate - stop_dist
        if self.be_floor and trade.max_rate:
            if trade.max_rate - trade.open_rate >= self.be_arm_r * stop_dist:
                stop_price = max(stop_price, trade.open_rate + self.be_buffer_atr * atr_entry)
        return stoploss_from_absolute(stop_price, current_rate, is_short=False, leverage=lev)

    # ------------------------------------------------------------------ P2
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        if not self.cluster_circuit:
            return True
        is_short = side == "short"
        since_block = current_time - timedelta(hours=self.circuit_hours)
        try:
            closed = Trade.get_trades_proxy(is_open=False)
        except Exception:
            return True
        same_dir_losses = [
            t for t in closed
            if t.exit_reason == "stop_loss"
            and (t.close_profit or 0.0) < 0.0
            and t.is_short == is_short
            and t.close_date_utc and t.close_date_utc >= since_block
        ]
        if not same_dir_losses:
            return True
        last_stop = max(t.close_date_utc for t in same_dir_losses)
        # circuit active: within circuit_hours of a stop that itself completed
        # a same-direction cluster (>= cluster_stop_count inside cluster_window_h)
        cluster_n = sum(
            1 for t in same_dir_losses
            if last_stop - timedelta(hours=self.cluster_window_h) <= t.close_date_utc <= last_stop
        )
        return cluster_n < self.cluster_stop_count

    # ------------------------------------------------------------------ P3
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        if (current_time - trade.open_date_utc).days >= self.time_stop_days:
            if not (self.time_stop_exempt and current_profit >= self.time_stop_exempt_profit):
                return "time_stop_60d"
        return None


# ---------------------------------------------------------------------------
# All-off sanity variant: must reproduce the OPT4 baseline byte-for-byte
# (proves the bug fix is inert in normal operation and P1-P3 are all off).
# ---------------------------------------------------------------------------
class OPT9_Off(OPT9_VolatilitySystem):
    be_floor = False
    cluster_circuit = False
    time_stop_exempt = False


# Ablation variants (single-mechanism runs for the pre-registered protocol)
class OPT9a_BEFloor(OPT9_VolatilitySystem):
    """P1 only."""
    cluster_circuit = False
    time_stop_exempt = False


class OPT9b_Circuit(OPT9_VolatilitySystem):
    """P2 only."""
    be_floor = False
    time_stop_exempt = False


class OPT9c_Exempt(OPT9_VolatilitySystem):
    """P3 only."""
    be_floor = False
    cluster_circuit = False


# Pre-registered follow-up (single point, no grid): arm=2.5R sits at the
# far edge of the 2023H1 forensic "empty zone" (winners' final MFE/stop_dist
# >= 2.3, immediate-losers <= 0.75). 1.5R falsified because too many winners
# arm mid-path and retest the entry zone; 2.5R only arms committed trends.
class OPT9d_BEFloor25(OPT9_VolatilitySystem):
    """P1 only, arm=2.5R."""
    be_arm_r = 2.5
    cluster_circuit = False
    time_stop_exempt = False
