# -*- coding: utf-8 -*-
"""LV1 统一回测产物分析器 — 口径与 research_revive/slowa 对齐后固定。

用法: python analyze_zip.py <zip1> <StrategyName1> [<zip2> <StrategyName2> ...]
输出: 每个变体 — 逐年(收益%/笔数/胜率%/PF/毛盈/毛亏/强平) + 全窗 maxDD%、
最差30d滚动DD%、总笔数、总PF、终值。

口径:
- 年收益: wallet feather -> D resample last -> groupby(year) first/last;
  末年 YE 用 JSON final_balance 锚定(已知坑: 最后一根K线平仓不计入 feather 末端)。
- maxDD / 30d滚动DD: 日线权益曲线全窗口。
- 毛盈/毛亏: sum(profit_abs>0) / sum(profit_abs<0), USDT, 含 funding_fees
  (freqtrade 的 profit_abs 已含 funding)。
"""
import json
import sys
import zipfile

import pandas as pd


def analyze(zip_path: str, strat_name: str) -> dict:
    z = zipfile.ZipFile(zip_path)
    names = z.namelist()
    jname = [n for n in names if n.endswith(".json") and "config" not in n][0]
    d = json.loads(z.read(jname))
    s = d["strategy"][strat_name]
    final_balance = float(s["final_balance"])
    start_balance = float(s["dry_run_wallet"])

    wname = [n for n in names if n.endswith("_wallet.feather")][0]
    w = pd.read_feather(z.open(wname))
    w["date"] = pd.to_datetime(w["date"], utc=True)
    eq = w.set_index("date")["total_quote"].resample("D").last().ffill()
    # 末值锚定
    eq.iloc[-1] = final_balance

    # ---- 全窗口 dd ----
    roll_max = eq.cummax()
    maxdd = float((eq / roll_max - 1.0).min())
    roll30 = eq / eq.rolling(30).max() - 1.0
    dd30 = float(roll30.min())

    # ---- 逐年 ----
    yearly = {}
    ye = eq.groupby(eq.index.year).last()
    y0 = eq.groupby(eq.index.year).first()
    # 首年起点 = start_balance(曲线第一天即有值,但保险起见锚定)
    y0.iloc[0] = start_balance
    ft_maxdd = float(s["max_drawdown_account"])
    trades = pd.DataFrame(s["trades"])
    trades["close_date"] = pd.to_datetime(trades["close_date"], utc=True)
    trades["year"] = trades["close_date"].dt.year
    for yr in ye.index:
        ret = ye[yr] / y0[yr] - 1.0
        t = trades[trades["year"] == yr]
        gp = float(t.loc[t["profit_abs"] > 0, "profit_abs"].sum())
        gl = float(t.loc[t["profit_abs"] <= 0, "profit_abs"].sum())
        wins = int((t["profit_abs"] > 0).sum())
        n = len(t)
        eq_y = eq[eq.index.year == yr]
        eq_y = pd.concat([pd.Series([y0[yr]]), eq_y])  # 含年初锚
        ydd = float((eq_y / eq_y.cummax() - 1.0).min())
        ydd30 = float((eq_y / eq_y.rolling(30).max() - 1.0).min())
        yearly[int(yr)] = {
            "ret_pct": round(ret * 100, 1),
            "trades": n,
            "winrate_pct": round(wins / n * 100, 1) if n else None,
            "pf": round(gp / abs(gl), 2) if gl else None,
            "gross_profit": round(gp, 0),
            "gross_loss": round(gl, 0),
            "liquidations": int((t["exit_reason"] == "liquidation").sum()),
            "maxdd_pct": round(ydd * 100, 1),
            "dd30_pct": round(ydd30 * 100, 1),
        }

    gp_all = float(trades.loc[trades["profit_abs"] > 0, "profit_abs"].sum())
    gl_all = float(trades.loc[trades["profit_abs"] <= 0, "profit_abs"].sum())
    return {
        "zip": zip_path,
        "strategy": strat_name,
        "start": start_balance,
        "final": round(final_balance, 0),
        "total_ret_pct": round(final_balance / start_balance * 100 - 100, 1),
        "trades": len(trades),
        "pf": round(gp_all / abs(gl_all), 2),
        "winrate_pct": round((trades["profit_abs"] > 0).mean() * 100, 1),
        "maxdd_pct": round(maxdd * 100, 1),
        "ft_maxdd_pct": round(ft_maxdd * 100, 1),
        "dd30_pct": round(dd30 * 100, 1),
        "liquidations": int((trades["exit_reason"] == "liquidation").sum()),
        "force_exits": int((trades["exit_reason"] == "force_exit").sum()),
        "yearly": yearly,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    for i in range(0, len(args), 2):
        r = analyze(args[i], args[i + 1])
        print("=" * 72)
        print(f"{r['strategy']}  {r['zip']}")
        print(f"总收益 {r['total_ret_pct']}%  终值 {r['final']}  笔数 {r['trades']}  "
              f"PF {r['pf']}  胜率 {r['winrate_pct']}%  maxDD(ft) {r['ft_maxdd_pct']}%  "
              f"maxDD(曲线) {r['maxdd_pct']}%  dd30 {r['dd30_pct']}%  "
              f"强平 {r['liquidations']}  force_exit {r['force_exits']}")
        hdr = ("year", "ret%", "n", "win%", "PF", "grossP", "grossL", "liq",
               "maxDD%", "dd30%")
        print(("{:>6} {:>7} {:>4} {:>6} {:>5} {:>9} {:>9} {:>4} {:>7} {:>7}").format(*hdr))
        for yr, y in r["yearly"].items():
            print(("{:>6} {:>7} {:>4} {:>6} {:>5} {:>9} {:>9} {:>4} {:>7} {:>7}").format(
                yr, y["ret_pct"], y["trades"], y["winrate_pct"], y["pf"],
                y["gross_profit"], y["gross_loss"], y["liquidations"],
                y["maxdd_pct"], y["dd30_pct"]))
