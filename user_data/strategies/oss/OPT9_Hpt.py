"""OPT9_Hpt — pre-registered hyperopt variant for research_ab Hyperopt-A (2026-11-04).

Purpose: answer "can the frozen parameters be SIGNIFICANTLY beaten?" on the
sleeve-A flagship line OPT9_Recycle -> ARL_2x (RECYCLE_MULT=1.21, lev 2x).
This is a verification/falsification experiment, NOT a hunt for a new
champion. Prior repo evidence (research_deepen/inference/report.md): rank IC
-0.156 over 75-config CSCV grid (~787 trials on record) => expected gain from
further tuning of signal/stop/resample ~= 0. Any "winner" found here must be
read against that prior and discounted for multiple testing.

New file only — OPT9_VolatilitySystem.py / AB_LevGrid.py remain untouched
(frozen). This subclass only:
  * re-declares the inherited OPT1 hyperopt parameters on PRE-REGISTERED
    categorical grids (no continuous widening):
      buy space  (entry side — DISCLOSURE: re-opens the frozen entry geometry,
                  falsified-direction discipline is knowingly suspended for
                  this one verification experiment):
        signal_atr_mult in {1.5, 1.75, 2.0, 2.25, 2.5}   (frozen default 2.0)
        resample_hours   in {2, 3, 4, 6}                 (frozen default 3)
      sell space (exit / risk-governance side):
        stop_atr_mult    in {1.5, 1.75, 2.0, 2.25, 2.5, 3.0}  (default 2.0)
        cluster_stop_count in {2, 3}                     (OPT9 P2 default 2)
        cluster_window_h   in {24, 48}                   (P2 default 24)
        circuit_hours      in {24, 48, 72}               (P2 default 48)
    risk_pct stays OUT (risk-model constant, separate research line).
  * overrides OPT9.confirm_trade_entry ONLY to cast the P2 knobs through
    .value — the Parameter objects do not implement __int__/__float__, and
    the frozen parent reads them as plain attributes. Logic is otherwise
    line-identical to OPT9_VolatilitySystem.confirm_trade_entry.

Space semantics (verified against freqtrade 2026.8 source): every epoch sets
attr.value on the live strategy instance and re-runs the FULL backtest
(including custom_stoploss / custom_stake_amount / confirm_trade_entry
callbacks), so sell-space knobs used inside callbacks are correctly varied.
resample_hours lives in populate_indicators -> hyperopt MUST use
--analyze-per-epoch (same note as OPT1, whose defaults came from exactly
this mechanism on IS 2021-2022).

Total grid = 5*4 (buy) x 6*2*2*3 (sell) = 20 x 72 = 1440 combinations.
"""
from datetime import datetime, timedelta

from freqtrade.persistence import Trade
from freqtrade.strategy import CategoricalParameter

from AB_LevGrid import ARL_2x


class OPT9_Hpt(ARL_2x):
    """Hyperopt vehicle. Baseline ARL_2x behavior is recovered exactly when
    every parameter sits at its default (the first random_state-42 epoch
    seed is the default point)."""

    # --- entry side (buy space) — re-opens frozen entry geometry (disclosed) ---
    signal_atr_mult = CategoricalParameter(
        [1.5, 1.75, 2.0, 2.25, 2.5], default=2.0, space="buy")
    resample_hours = CategoricalParameter(
        [2, 3, 4, 6], default=3, space="buy")

    # --- exit side (sell space) ---
    stop_atr_mult = CategoricalParameter(
        [1.5, 1.75, 2.0, 2.25, 2.5, 3.0], default=2.0, space="sell")

    # --- P2 circuit-breaker side (sell space — risk governance) ---
    cluster_stop_count = CategoricalParameter(
        [2, 3], default=2, space="sell")
    cluster_window_h = CategoricalParameter(
        [24, 48], default=24, space="sell")
    circuit_hours = CategoricalParameter(
        [24, 48, 72], default=48, space="sell")

    # ------------------------------------------------------------------ P2
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        """Line-identical to OPT9_VolatilitySystem.confirm_trade_entry except
        the three P2 knobs are read through .value with explicit casts."""
        if not self.cluster_circuit:
            return True
        is_short = side == "short"
        circuit_hours = float(self.circuit_hours.value)
        cluster_window_h = float(self.cluster_window_h.value)
        cluster_stop_count = int(self.cluster_stop_count.value)
        since_block = current_time - timedelta(hours=circuit_hours)
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
            if last_stop - timedelta(hours=cluster_window_h) <= t.close_date_utc <= last_stop
        )
        return cluster_n < cluster_stop_count
