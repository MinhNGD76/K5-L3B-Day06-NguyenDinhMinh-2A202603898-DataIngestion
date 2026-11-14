"""Turn the filled coherence/grounding label files into the report's numbers.

Run from starter/ after filling results/manual/*_labels.csv:  python -m scripts.score_manual_audit
Refuses to run if any score is blank or not 0/1/2, or any reason is empty.
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "manual"
key = json.loads((OUT / "key.json").read_text(encoding="utf-8"))


def read_labels(name: str) -> dict[str, int]:
    rows = list(csv.DictReader((OUT / name).open(encoding="utf-8")))
    bad = [r["id"] for r in rows if r["score"].strip() not in ("0", "1", "2") or not r["reason"].strip()]
    if bad:
        raise SystemExit(f"{name}: missing/invalid score or reason for {bad}")
    return {r["id"]: int(r["score"]) for r in rows}


coherence = read_labels("coherence_labels.csv")
grounding = read_labels("grounding_labels.csv")
scores = {s: {"coherence": [], "grounding": []} for s in "ABC"}
for cid, v in coherence.items():
    index = key["coherence"][cid]["index"]
    for s in ("A",) if index == "A" else ("B", "C"):  # C uses B's chunks
        scores[s]["coherence"].append(v)
for gid, v in grounding.items():
    for s in key["grounding"][gid]["strategies"]:
        scores[s]["grounding"].append(v)

meta = json.loads((OUT / "metadata_summary.json").read_text(encoding="utf-8"))
summary = {}
for s, d in scores.items():
    g = Counter(d["grounding"])
    summary[s] = {
        "coherence_mean": round(sum(d["coherence"]) / len(d["coherence"]), 2), "coherence_n": len(d["coherence"]),
        "grounding_counts_0_1_2": [g[0], g[1], g[2]], "grounding_n": len(d["grounding"]),
        "grounding_mean": round(sum(d["grounding"]) / len(d["grounding"]), 2),
        "metadata_ok": f"{meta[s]['ok']}/{meta[s]['total']}"}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
for s, v in summary.items():
    print(f"{s}: coherence {v['coherence_mean']}/2 (n={v['coherence_n']}) | metadata {v['metadata_ok']} | "
          f"grounding 0/1/2 = {'/'.join(map(str, v['grounding_counts_0_1_2']))} mean {v['grounding_mean']}/2 "
          f"(n={v['grounding_n']})")
