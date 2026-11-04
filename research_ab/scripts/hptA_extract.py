"""Extract per-strategy summary metrics from freqtrade backtesting console logs
(works for --strategy-list runs: splits on 'Result for strategy')."""
import re
import sys

PATS = [
    ("profit%", r"Total profit %\s+│ ([\d.\-]+)%"),
    ("CAGR%", r"CAGR %\s+│ ([\d.\-]+)%"),
    ("maxDD%", r"Max % of account underwater\s+│ ([\d.\-]+)%"),
    ("SharpeD", r"Sharpe \(daily wallet balance\)\s+│ ([\d.\-]+)"),
    ("SortinoD", r"Sortino \(daily wallet balance\)\s+│ ([\d.\-]+)"),
    ("CalmarD", r"Calmar \(daily wallet balance\)\s+│ ([\d.\-]+)"),
    ("trades", r"Total/Daily Avg Trades\s+│ (\d+)"),
    ("PF", r"Profit factor\s+│ ([\d.]+)"),
    ("win%", r"Win% \(of closed\)\s+│ ([\d.]+)|Win  Draw  Loss  Win%.*?│.*?(\d+\.\d) *│"),
]


def extract(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    out = []
    for b in re.split(r"Result for strategy ", txt)[1:]:
        name = b.split("\n")[0].strip()
        row = {"strategy": name}
        for k, p in PATS:
            m = re.search(p, b)
            row[k] = m.group(1) if m and m.lastindex and m.group(m.lastindex) else (m.group(1) if m else "?")
        out.append(row)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(f"== {path} ==")
        hdr = ["strategy"] + [k for k, _ in PATS]
        rows = extract(path)
        print(" | ".join(f"{h:>9}" for h in hdr))
        for r in rows:
            print(" | ".join(f"{str(r.get(h, '?')):>9}" for h in hdr))
        print()
