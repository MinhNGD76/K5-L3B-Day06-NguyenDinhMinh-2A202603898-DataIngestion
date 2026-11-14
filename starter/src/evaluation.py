"""Automatic retrieval metrics and per-query traces. Manual labels live elsewhere."""
from collections import defaultdict
from typing import Any

from .ingestion import normalize_text


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """A hit = chunk from the gold source/page that contains a whole gold evidence quote
    (main or any documented alternative). Coherence/grounding are NOT inferred here."""
    golds = [(question["gold_page"], question["evidence_quote"])]
    golds += [(a["page"], a["quote"]) for a in question.get("alt_evidence", [])]
    golds = [(p, normalize_text(q)) for p, q in golds]
    gold_pages = {p for p, _ in golds}

    def is_hit(h: dict[str, Any]) -> bool:
        return h["document_id"] == question["gold_source_id"] and any(
            h["page"] == p and q in h["text"] for p, q in golds)

    flags = [is_hit(h) for h in hits[:3]]
    flt = question.get("filter")
    return {
        "id": question["id"], "split": question["split"], "type": question["type"],
        "question": question["question"], "filter": flt,
        "hit_at_1": bool(flags) and flags[0],
        "hit_at_3": any(flags),
        "first_hit_rank": flags.index(True) + 1 if any(flags) else None,
        # diagnostic: right chapter in top-3 but no chunk holds the whole quote (split evidence)
        "gold_page_at_3": any(h["page"] in gold_pages for h in hits[:3]),
        "filter_ok": None if not flt else all(h.get(k) == v for h in hits[:3] for k, v in flt.items()),
        "hits": [{"rank": r, "chunk_id": h["chunk_id"], "page": h["page"],
                  "unit_id": h["metadata"].get("unit_id"), "book": h.get("book"),
                  "score": round(float(h["score"]), 4), "evidence_hit": f, "text": h["text"]}
                 for r, (h, f) in enumerate(zip(hits[:3], flags), start=1)],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts (not just %) per strategy and split. Traces need a 'strategy' key."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in traces:
        groups[f"{t['strategy']}/{t['split']}"].append(t)
    out = {}
    for key, ts in sorted(groups.items()):
        filtered = [t for t in ts if t["filter"]]
        out[key] = {
            "N": len(ts),
            "hit_at_1": sum(t["hit_at_1"] for t in ts),
            "hit_at_3": sum(t["hit_at_3"] for t in ts),
            "gold_page_at_3": sum(t["gold_page_at_3"] for t in ts),
            "filter_questions": len(filtered),
            "filter_ok": sum(bool(t["filter_ok"]) for t in filtered) if filtered else None,
        }
    return out
