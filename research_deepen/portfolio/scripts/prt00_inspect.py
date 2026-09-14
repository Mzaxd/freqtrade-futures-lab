"""PRT00: inspect sleeve zips -> strategy/timeframe/window/daily_profit availability + wallet feather structure."""
import json, glob, os, sys

BASE = r"D:\Code\AIQuant\freqtrade-futures-lab\research_deepen\portfolio\results\inspect"
ZIPS = {
    "A_opt4": "opt4_VolatilitySystem_12p_is",
    "N_lite": "opt7_lite_tc3_12p_is",
    "S_superdd": "opt7_pool12_A_OPT7_SuperDD_A",
    "B_is": "opt2_MomRegime15mLb21_is",
    "B_val": "opt2_MomRegime15mLb21_val",
}

for tag, z in ZIPS.items():
    main = glob.glob(os.path.join(BASE, z, "backtest-result-*.json"))
    main = [m for m in main if not m.endswith("_config.json")][0]
    d = json.load(open(main))
    strat = d["strategy"]
    print(f"=== {tag} ({z}) ===")
    print("  backtest_start/end:", d.get("backtest_start"), "->", d.get("backtest_end"))
    print("  timeframe:", d.get("timeframe"), " strategy keys:", len(strat))
    for name, s in strat.items():
        print(f"  strategy={name} trades={len(s.get('trades', []))} profit_total={s['profit_total']*100:.2f}% maxdd={s.get('max_drawdown_account',0)*100:.2f}%")
        print("   keys sample:", [k for k in s.keys() if 'daily' in k.lower() or 'period' in k.lower()])
        dp = s.get("daily_profit")
        if dp:
            print("   daily_profit: n=", len(dp), " first:", dp[0], " last:", dp[-1])
        # trade sample
        tr = s.get("trades", [])
        if tr:
            t0 = tr[0]
            print("   trade keys:", sorted(t0.keys()))
            # durations
            from datetime import datetime
            def parse(x): return datetime.fromisoformat(x.replace("Z", "+00:00")) if isinstance(x, str) else x
            durs = [(parse(t["close_date"]) - parse(t["open_date"])).total_seconds() / 3600 for t in tr]
            durs.sort()
            print(f"   hold hours: p50={durs[len(durs)//2]:.1f} p90={durs[int(len(durs)*0.9)]:.1f} max={durs[-1]:.1f}")
            print(f"   first open {tr[0]['open_date']} last close {tr[-1]['close_date']}")
    # wallet feather
    wf = glob.glob(os.path.join(BASE, z, "*_wallet.feather"))
    if wf:
        import pandas as pd
        w = pd.read_feather(wf[0])
        print("  wallet feather:", w.shape, "cols:", list(w.columns)[:10])
        print("   head:\n", w.head(3).to_string())
        print("   tail:\n", w.tail(3).to_string())
    print()
