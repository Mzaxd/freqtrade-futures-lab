# OPT4_Struct_variants — Phase-4 structure/exposure experiment cells (Agent-H).
# All cells keep OPT1 signal/resample/stop parameters frozen (2.0 / 3h / 2.0).
# Gates: see OPT4_Struct_gate.py. B/C/D cells inherit OPT1 directly.
from datetime import datetime

from pandas import DataFrame

from freqtrade.persistence import Trade

from OPT1_VolatilitySystem import OPT1_VolatilitySystem
from OPT4_Struct_gate import OPT4_Struct_gate


# ---------------------------------------------------------------- A. regime gates
class OPT4_Struct_Adx15(OPT4_Struct_gate):
    """ADX(14)@1h >= 15 gate on new entries."""
    gate_mode = "adx"
    adx_threshold = 15.0


class OPT4_Struct_Adx20(OPT4_Struct_gate):
    """ADX(14)@1h >= 20 gate on new entries."""
    gate_mode = "adx"
    adx_threshold = 20.0


class OPT4_Struct_Adx25(OPT4_Struct_gate):
    """ADX(14)@1h >= 25 gate on new entries."""
    gate_mode = "adx"
    adx_threshold = 25.0


class OPT4_Struct_AtrPct08(OPT4_Struct_gate):
    """resampled ATR >= 0.8 x its rolling 30d median gate on new entries."""
    gate_mode = "atr_pct"
    atr_gate_mult = 0.8


class OPT4_Struct_AtrPct10(OPT4_Struct_gate):
    """resampled ATR >= 1.0 x its rolling 30d median gate on new entries."""
    gate_mode = "atr_pct"
    atr_gate_mult = 1.0


class OPT4_Struct_Cool48(OPT4_Struct_gate):
    """48h re-entry cooldown after a stoploss exit, per pair."""
    gate_mode = "cooldown"
    cooldown_hours = 48


class OPT4_Struct_Cool96(OPT4_Struct_gate):
    """96h re-entry cooldown after a stoploss exit, per pair."""
    gate_mode = "cooldown"
    cooldown_hours = 96


# ---------------------------------------------------------------- B. time stop
class OPT4_Struct_TimeStop60(OPT1_VolatilitySystem):
    """Force-close trades still open after 60 days (lab 28d cut killed the 121d winners)."""
    time_stop_days = 60

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        if (current_time - trade.open_date_utc).days >= self.time_stop_days:
            return "time_stop_60d"
        return None


# ---------------------------------------------------------------- D. leverage
class OPT4_Struct_Lev3(OPT1_VolatilitySystem):
    """3x instead of 2x. 1%-risk sizing unchanged: same notional, less margin, thinner liq buffer."""
    leverage_fixed = 3.0
