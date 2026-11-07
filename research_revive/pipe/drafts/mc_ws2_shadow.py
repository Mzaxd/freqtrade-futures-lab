# -*- coding: utf-8 -*-
"""mc_ws2_shadow.py — 草案,未运行(research_revive/pipe/drafts/)。

方案3 P2 步:★ 组合(A_vt60f1 + B_2xvt, 7000/3000)WS2 式块自助蒙特卡洛。
惯例复用:
  - research_ab/ws2_analysis.py:对 (rA, rB) 同日联合块自助(保袖间相关),
    块长 30d、2000 路、固定 seed;30d 滚动 DD 最深 -> 分位 + P(触 -20%)
  - research_deepen/inference/scripts/inf_bootstrap.py:iid(块长 1)对照
  - research_deepen/portfolio/scripts/prt08_wboot.py:平稳自助(均值块 10d)敏感性
  - research_improve/CONTEXT.md §6:袖曲线提取标准法
    (zip 内 <strategy>_wallet.feather -> resample('h').last().ffill() ->
     两袖相加;末端用 profit_total_abs 锚定 —— 末根强平/未平仓不计入 feather 的已知坑)

输出(P3 红线复核与 P5 影子判定带的输入):
  (a) 全窗 dd30 最深分布 p5/p50/p95、P(dd30 <= -20%)
  (b) 180d 影子期窗口:末收益分布 P(<0)/P10/P50/P90、窗口内 dd30 最深 p95
  (c) 月度收益 P10-P90 带(影子期月评审对照)
  (d) iid 对照(块结构对尾部 DD 的贡献)

执行时复制到 research_revive/pipe/mc_ws2_shadow.py 运行:
  PYTHONIOENCODING=utf-8 python research_revive/pipe/mc_ws2_shadow.py \
      > research_revive/pipe/results_mc.json
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

ZIP_A = ROOT / "user_data/backtest_results/backtest-result-2026-11-07_06-45-22.zip"  # port_a_vt60f1
ZIP_B = ROOT / "user_data/backtest_results/lvg_full_b_2xvt.zip"
STRAT_A = "LVG_A_vt60f1"
STRAT_B = "LVG_B_2xvt"

SEED = 20261107          # 固定 seed(ws2 惯例:日期式)
N_MC = 2000              # 路径数(ws2 惯例)
BLOCK = 30               # 块长(天,ws2 惯例)
DD_LINE = -0.20          # 章程红线
SHADOW_WIN = 180         # 影子期窗口(天)
MONTHS_OUT = 8           # 月度带输出最近 N 个月


def wallet_curve(zpath: Path, strat: str) -> pd.Series:
    """zip 内 wallet feather -> 锚定终值的日权益序列(CONTEXT §6 标准法)。"""
    with zipfile.ZipFile(zpath) as z:
        wf = [n for n in z.namelist() if n.endswith("_wallet.feather")]
        assert len(wf) == 1, f"{zpath}: 预期恰一个 wallet feather, 实得 {wf}"
        eq = pd.read_feather(io.BytesIO(z.read(wf[0])))
        s = eq.set_index(pd.DatetimeIndex(pd.to_datetime(eq["date"], utc=True)))["total_quote"]
        s = s.resample("h").last().ffill()
        # 锚定:结果 JSON 的 profit_total_abs(末端强平/未平仓 PnL 不在 feather 末端)
        jn = [n for n in z.namelist() if n.endswith(".json")
              and not n.endswith(("_config.json", "_config.json.meta.json"))][0]
        res = json.loads(z.read(jn))
        st = res["strategy"][strat]
        anchored = st["starting_balance"] + st["profit_total_abs"]
        s.iloc[-1] = anchored
    return s.resample("D").last().dropna()


def block_paths(rA: np.ndarray, rB: np.ndarray, n_mc: int, block: int,
                rng: np.random.Generator):
    """联合块自助生成器:同日 (rA, rB) 成对重采样,逐路径 yield (pA, pB)。"""
    n = len(rA)
    n_blocks = int(np.ceil(n / block))
    for _ in range(n_mc):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        yield rA[idx], rB[idx]


def dd30_min(daily: np.ndarray) -> float:
    eq = np.cumprod(1.0 + daily)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    out = 0.0
    for i in range(len(eq)):
        w = peak[max(0, i - 30):i + 1].max()
        out = min(out, eq[i] / w - 1.0)
    return float(out)


def main() -> None:
    a = wallet_curve(ZIP_A, STRAT_A)
    b = wallet_curve(ZIP_B, STRAT_B)
    idx = a.index.intersection(b.index)
    a, b = a.loc[idx], b.loc[idx]
    rA = a.pct_change().dropna().values
    rB = b.pct_change().dropna().values
    assert len(rA) == len(rB)

    def combo_monthly(pA, pB):
        eA, eB = np.cumprod(1 + pA), np.cumprod(1 + pB)
        tot = eA + eB
        return tot

    out = {"seed": SEED, "n_mc": N_MC, "block": BLOCK,
           "window": {"start": str(idx[0].date()), "end": str(idx[-1].date()),
                      "days": len(rA)}}

    for tag, blk in [("block30", BLOCK), ("iid1", 1)]:
        rng = np.random.default_rng(SEED)
        dd_all, final180, dd180, monthly_bands = [], [], [], {}
        for pA, pB in block_paths(rA, rB, N_MC, blk, rng):
            tot = combo_monthly(pA, pB)
            ret = tot[1:] / tot[:-1] - 1.0
            dd_all.append(dd30_min(ret))
            i0 = max(0, len(ret) - SHADOW_WIN)
            w = ret[i0:]
            eq = np.cumprod(1 + w)
            dd180.append(dd30_min(w))
            final180.append(eq[-1] - 1.0)
            m = pd.Series(eq, index=idx[1:][i0:]).resample("ME").last().pct_change().dropna()
            for k, v in m.items():
                monthly_bands.setdefault(k.strftime("%Y-%m"), []).append(float(v))
        out[tag] = {
            "dd30_all": {"p5": np.percentile(dd_all, 5), "p50": np.percentile(dd_all, 50),
                         "p95": np.percentile(dd_all, 95),
                         "p_le_-20": float(np.mean(np.array(dd_all) <= DD_LINE))},
            "shadow_180d": {"final_ret_p10": np.percentile(final180, 10),
                            "final_ret_p50": np.percentile(final180, 50),
                            "final_ret_p90": np.percentile(final180, 90),
                            "p_final_neg": float(np.mean(np.array(final180) < 0)),
                            "dd30_p95": np.percentile(dd180, 95)},
            "monthly_band": {m: {"p10": np.percentile(v, 10), "p50": np.percentile(v, 50),
                                 "p90": np.percentile(v, 90)}
                             for m, v in sorted(monthly_bands.items())[-MONTHS_OUT:]},
        }
        print(f"[{tag}] done", file=__import__("sys").stderr)

    print(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
