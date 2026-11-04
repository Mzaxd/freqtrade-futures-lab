"""OPT9 risk-sizing variants — quantify the risk_pct dial on the full 2021-26 window.

Parent research (commit babfdfe) concluded risk_pct is the real risk dial
(leverage is neutral). These subclasses change ONLY the risk_pct constant:
0.005 (half risk) and 0.0025 (quarter risk) vs the flagship 0.01.
Everything else (entries, exits, circuit breaker, leverage) byte-identical.
"""
from OPT9_VolatilitySystem import OPT9_VolatilitySystem


class OPT9_RiskHalf(OPT9_VolatilitySystem):
    risk_pct = 0.005


class OPT9_RiskQuarter(OPT9_VolatilitySystem):
    risk_pct = 0.0025
