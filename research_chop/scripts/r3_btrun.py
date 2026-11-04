"""r3_btrun.py — serial backtest runner with zip-identity verification.

Usage: python r3_btrun.py <StrategyClass> <timerange> <tag> [strategy_path]

Runs ONE freqtrade backtest (serial discipline), then identifies the newest
backtest-result zip, verifies the JSON 'strategy' key matches the expected
class (plus trade count > 0), and moves it to
research_chop/results/R3_<tag>.zip. Aborts loudly on mismatch (mislabelled
zip race lesson from CONTEXT.md technical red line #2).
"""
import glob
import json
import os
import subprocess
import sys
import time
import zipfile

ROOT = r"D:\Code\AIQuant\freqtrade-futures-lab"
FT = os.path.join(ROOT, ".venv", "Scripts", "freqtrade.exe")
RES = os.path.join(ROOT, "research_chop", "results")
LOGS = os.path.join(ROOT, "research_chop", "logs")
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]


def newest_zip():
    zips = sorted(glob.glob(os.path.join(ROOT, "user_data", "backtest_results",
                                         "backtest-result-*.zip")),
                  key=os.path.getmtime)
    return zips[-1] if zips else None


def main() -> int:
    strat, timerange, tag = sys.argv[1:4]
    expected = int(sys.argv[4]) if len(sys.argv) > 4 else 0   # exact trade count (0 = skip)
    spath = sys.argv[5] if len(sys.argv) > 5 else os.path.join(ROOT, "research_chop", "strategies")
    before = newest_zip()
    before_mt = os.path.getmtime(before) if before else 0
    cmd = [FT, "backtesting", "--userdir", "user_data",
           "--config", "user_data/configs/OPT7_config_12p.json",
           "--strategy-path", spath, "--strategy", strat,
           "--timerange", timerange, "-p"] + PAIRS + \
          ["--export", "trades", "--cache", "none"]
    log = os.path.join(LOGS, f"r3_{tag}_console.log")
    with open(log, "wb") as lf:
        rc = subprocess.call(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
    if rc != 0:
        print(f"FAIL rc={rc} for {strat}; see {log}")
        return 1
    time.sleep(4)   # freqtrade holds the zip briefly after exit
    z = newest_zip()
    if z is None or os.path.getmtime(z) == before_mt:
        print(f"FAIL no new zip produced for {strat}")
        return 1
    for attempt in range(6):
        try:
            with zipfile.ZipFile(z) as f:
                nm = [n for n in f.namelist() if n.endswith(".json")
                      and "config" not in n and "market" not in n and "meta" not in n][0]
                d = json.loads(f.read(nm))
            break
        except Exception as e:
            print(f"  zip busy/invalid ({e}), retry {attempt + 1}")
            time.sleep(4)
            z = newest_zip()
    else:
        print(f"FAIL cannot read zip for {strat}")
        return 1
    keys = list(d["strategy"].keys())
    s = list(d["strategy"].values())[0]
    n_tr = len(s["trades"])
    prof = round(s["profit_total"] * 100, 2)
    per_pair = {}
    for t in s["trades"]:
        per_pair[t["pair"]] = per_pair.get(t["pair"], 0) + 1
    print(f"  zip {os.path.basename(z)} -> strategy={keys} trades={n_tr} profit%={prof} "
          f"window={s['backtest_start'][:10]}..{s['backtest_end'][:10]} pairs={per_pair}")
    if keys != [strat]:
        print(f"FAIL identity mismatch: expected [{strat}] got {keys} — NOT moving")
        return 1
    if expected and n_tr != expected:
        print(f"FAIL trade-count guard: expected {expected} got {n_tr} — NOT moving "
              f"(universe/corruption check)")
        return 1
    dst = os.path.join(RES, f"R3_{tag}.zip")
    for attempt in range(6):
        try:
            os.rename(z, dst)
            break
        except PermissionError:
            time.sleep(4)
    else:
        print(f"FAIL could not move {z} (locked)")
        return 1
    print(f"OK {strat} [{timerange}] -> R3_{tag}.zip  ({n_tr} trades, {prof}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
