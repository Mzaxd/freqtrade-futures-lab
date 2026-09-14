"""PRT01: scan all backtest zips for sleeve strategies and their windows; verify A/A8 configs."""
import json, zipfile, glob, os, io, sys

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab\user_data\backtest_results"
WANT = ("OPT2_MomRegime15mLb21", "OPT4_C2", "OPT4_VolatilitySystem", "OPT7_SuperDD_A", "OPT7_NFILite")

def first_last_trades(s):
    tr = s.get("trades", [])
    if not tr:
        return None, None, 0
    od = min(t["open_date"] for t in tr)
    cd = max(t["close_date"] for t in tr)
    return od, cd, len(tr)

hits = []
for z in sorted(glob.glob(os.path.join(ROOT, "*.zip"))):
    try:
        with zipfile.ZipFile(z) as f:
            mains = [n for n in f.namelist() if n.endswith(".json") and "_config" not in n]
            if not mains:
                continue
            d = json.loads(f.read(mains[0]))
            for name, s in d.get("strategy", {}).items():
                if any(w in name for w in WANT):
                    od, cd, n = first_last_trades(s)
                    hits.append((os.path.basename(z), name, n, od, cd,
                                 round(s.get("profit_total", 0) * 100, 2),
                                 round(s.get("max_drawdown_account", 0) * 100, 2)))
    except Exception as e:
        print("ERR", z, e)

print(f"{'zip':58s} {'strategy':36s} {'n':>5s} {'first_open':22s} {'last_close':22s} {'profit%':>9s} {'maxDD%':>7s}")
for h in hits:
    print(f"{h[0]:58s} {h[1]:36s} {h[2]:5d} {h[3]:22s} {h[4]:22s} {h[5]:9.2f} {h[6]:7.2f}")
