"""Verify benchmark/questions.json against the normalized corpus. Fails loudly.

Run from starter/:  python -m scripts.verify_benchmark [path/to/questions.json]
"""
import json
import sys
from collections import Counter
from pathlib import Path

from src.ingestion import load_chapters, normalize_text

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "starter" / "data" / "The Brothers Karamazov.txt"
REQUIRED = ["id", "split", "type", "question", "expected_answer", "gold_source_id",
            "gold_page", "gold_unit_id", "evidence_quote", "filter", "alt_evidence"]

pages = {p.page: p for p in load_chapters(CORPUS, "karamazov-pg28054", "")}
QUESTIONS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "benchmark" / "questions.json"
questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
errors = []


def check_quote(qid: str, page: int, unit_id: str, quote: str) -> None:
    p = pages.get(page)
    if p is None or p.metadata["unit_id"] != unit_id:
        errors.append(f"{qid}: page {page} is not unit {unit_id}")
    elif normalize_text(quote) not in p.text:
        errors.append(f"{qid}: evidence not found in page {page} ({unit_id})")
    elif sum(normalize_text(quote) in x.text for x in pages.values()) > 1:
        print(f"note {qid}: evidence also appears in another chapter")


for q in questions:
    if missing := [k for k in REQUIRED if k not in q]:
        errors.append(f"{q.get('id')}: missing {missing}")
        continue
    check_quote(q["id"], q["gold_page"], q["gold_unit_id"], q["evidence_quote"])
    for alt in q["alt_evidence"]:
        check_quote(q["id"] + "/alt", alt["page"], alt["unit_id"], alt["quote"])
    for field, value in (q["filter"] or {}).items():
        if pages[q["gold_page"]].metadata.get(field) != value:
            errors.append(f"{q['id']}: gold page does not satisfy filter {field}={value}")

ids = Counter(q["id"] for q in questions)
splits = Counter(q["split"] for q in questions)
filters = Counter(q["split"] for q in questions if q["filter"])
dev_pages = {q["gold_page"] for q in questions if q["split"] == "dev"}
leaks = [q["id"] for q in questions if q["split"] == "test" and q["gold_page"] in dev_pages]
errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
if splits["dev"] < 15 or splits["test"] < 5:
    errors.append(f"need >=15 dev / >=5 test, got {dict(splits)}")
if sum(filters.values()) < 3 or filters["test"] < 1:
    errors.append(f"need >=3 filter questions incl. >=1 test, got {dict(filters)}")
if leaks:
    errors.append(f"test questions share a gold chapter with dev: {leaks}")

if errors:
    raise SystemExit("FAILED\n" + "\n".join(errors))
print(f"OK: {len(questions)} questions {dict(splits)}, filter {dict(filters)}, "
      f"types {dict(Counter(q['type'] for q in questions))}, test chapters disjoint from dev")
