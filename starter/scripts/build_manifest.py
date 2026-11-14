"""Build data/manifest.json from the corpus and self-check the unit split.

Run from starter/:  python -m scripts.build_manifest
"""
import hashlib
import json
from datetime import date
from pathlib import Path

from src.ingestion import load_chapters, normalize_text

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "starter" / "data" / "The Brothers Karamazov.txt"
MIN_CHARS = 1500

assert normalize_text("a\r\nb  c\r\n  \r\n\r\nd") == "a b c\n\nd"

raw = CORPUS.read_text(encoding="utf-8")
pages = load_chapters(CORPUS, "karamazov-pg28054", CORPUS.relative_to(ROOT).as_posix())
contents_chapters = sum(1 for line in raw.splitlines() if line.startswith(" Chapter "))
assert len(pages) == contents_chapters, (len(pages), contents_chapters)
assert len({p.metadata["unit_id"] for p in pages}) == len(pages), "duplicate unit_id"
short = [p.metadata["unit_id"] for p in pages if len(p.text) < MIN_CHARS]
counted = [p for p in pages if len(p.text) >= MIN_CHARS]
assert len(counted) >= 30, len(counted)

manifest = {
    "source_id": "karamazov-pg28054",
    "title": "The Brothers Karamazov",
    "author": "Fyodor Dostoyevsky",
    "translator": "Constance Garnett",
    "language": "en",
    "source_path_or_url": CORPUS.relative_to(ROOT).as_posix(),
    "original_url": "https://www.gutenberg.org/ebooks/28054",
    "snapshot": "Project Gutenberg eBook #28054, release 2009-02-12, 'Most recently updated: September 18, 2026' (file header)",
    "license_or_permission": "Public domain in the USA per Project Gutenberg; redistributed unmodified with the Project Gutenberg License kept in the file. Author d. 1881, translator d. 1946.",
    # shortcut: date taken from the file's mtime (= download day); replace if the real access date differs
    "accessed_at": date.fromtimestamp(CORPUS.stat().st_mtime).isoformat(),
    "file_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
    "physical_lines": len(raw.splitlines()),
    "unit_rule": (
        "No physical pages. One unit = one chapter (GUIDE: independent meaningful source unit); "
        "`page` = chapter order 1..N. Counted if normalized text >= 1500 chars. "
        "Boundaries are 1-based line numbers in the original file (chapter body, excluding heading lines)."
    ),
    "excluded": [
        "Project Gutenberg header and license (outside START/END markers)",
        "Title page and table of contents (before the 'PART I' heading)",
        "Translator FOOTNOTES section at the end of the text",
        "Part/Book/Chapter heading lines (kept as metadata, not body text)",
    ],
    "filter_fields": {
        "part": "Part I..Part IV | Epilogue, from PART headings",
        "book": "Book I..Book XII | Epilogue, from 'Book N. Title' headings",
    },
    "unit_count": len(pages),
    "counted_units": len(counted),
    "short_units": short,
    "total_chars": sum(len(p.text) for p in pages),
    "units": [{"page": p.page, **p.metadata} for p in pages],
}

out = ROOT / "data" / "manifest.json"
out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{len(pages)} units, {len(counted)} counted (>= {MIN_CHARS} chars), "
      f"{manifest['total_chars']:,} chars, short={short} -> {out.relative_to(ROOT)}")
