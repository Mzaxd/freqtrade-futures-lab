"""Dispatcher cross-check (PRE_REG section 6): does the winning grid sleeve
fill A's actual hole?"""
import pandas as pd

ep = pd.read_csv("research_chop/logs/grid_episodes_OS.csv", parse_dates=["t_start", "t_end"])
win = ep[(ep.gate == "g2") & (ep["L"] == 12) & (ep.k == 0.5)
         & (ep["mode"] == "dual") & (ep["fill"] == "cross")].copy()
win["pnl"] = win.end_equity - win.start_equity
win["month_end"] = (win.t_end + pd.offsets.MonthEnd(0)).dt.tz_localize("UTC")

g = win.groupby("month_end")["pnl"].sum().rename("grid")
a3 = pd.read_csv("user_data/logs/mtm_daily_A3.csv", parse_dates=[0], index_col=0)
a3.columns = ["eq"]
am = a3.resample("ME").last()["eq"].pct_change().rename("A3")
m = pd.concat([g, am], axis=1).dropna()
print(f"months={len(m)}  corr(monthly grid PnL USD, A3 monthly %) = {m.grid.corr(m.A3):+.3f}")
print(f"grid total OS = {win.pnl.sum():+.0f} USD on 3x10000; positive months {(m.grid>0).mean():.0%}")

print("\nA3 worst 8 OS months vs grid PnL same month:")
print(m.nsmallest(8, "A3").assign(grid_usd=lambda d: d.grid.round(0)).round(4).to_string())

b = win[(win.t_end >= "2026-02-15") & (win.t_end <= "2026-08-10")]
print(f"\n2026-02-15..08-10 bleed: {len(b)} eps, PnL {b.pnl.sum():+.0f} (grid_profit {b.grid_profit.sum():+.0f}, clear {b.clear_pnl.sum():+.0f})")
b2 = win[(win.t_end >= "2025-10-01") & (win.t_end <= "2026-06-30")]
print(f"2025-10..2026-06 channel: {len(b2)} eps, PnL {b2.pnl.sum():+.0f}")
best = win.nlargest(5, "pnl")[["t_start","t_end","pair","pnl","grid_profit","clear_pnl"]]
print("\ngrid best 5 episodes (where the +3800 actually comes from):")
print(best.assign(pnl=lambda d: d.pnl.round(0)).to_string(index=False))
