"""Read and normalize source data."""
import re
import unicodedata
from pathlib import Path
from .models import DocumentPage

PART_RE = re.compile(r"^(PART [IV]+|EPILOGUE)$")
BOOK_RE = re.compile(r"^Book ([IVX]+)\. (.+)$")
CHAPTER_RE = re.compile(r"^Chapter ([IVX]+)\.$")


def load_chapters(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Split a Project Gutenberg novel into one traceable unit per chapter.

    The text has no physical pages, so `page` is the chapter's 1-based order in the
    novel; part/book/chapter come verbatim from the source headings. Front matter,
    the table of contents, translator footnotes and the PG license are excluded.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("PART I")  # first heading after the table of contents
    end = lines.index("FOOTNOTES")
    part = book = book_title = None
    units: list[dict] = []
    i = start
    while i < end:
        line = lines[i].strip()
        if PART_RE.match(line):
            part = "Epilogue" if line == "EPILOGUE" else "Part " + line.split()[1]
            if part == "Epilogue":
                book, book_title = "Epilogue", "Epilogue"
        elif m := BOOK_RE.match(line):
            book, book_title = f"Book {m.group(1)}", m.group(2)
        elif m := CHAPTER_RE.match(line):
            title_at = next(j for j in range(i + 1, end) if lines[j].strip())
            units.append({"part": part, "book": book, "book_title": book_title,
                          "chapter": m.group(1), "chapter_title": lines[title_at].strip(),
                          "line_start": title_at + 2})  # 1-based line after the title
            i = title_at
        elif units:
            units[-1]["line_end"] = i + 1
        i += 1

    pages = []
    for n, u in enumerate(units, start=1):
        text = normalize_text("\n".join(lines[u["line_start"] - 1:u["line_end"]]))
        book_code = "EP" if u["book"] == "Epilogue" else "B" + u["book"].split()[1]
        u.update(unit_id=f"{book_code}-C{u['chapter']}", char_count=len(text))
        pages.append(DocumentPage(document_id, source, n, text, u))
    return pages


def normalize_text(text: str) -> str:
    """NFC, unify line endings, unwrap hard-wrapped lines; keep paragraph breaks."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    paragraphs = re.split(r"\n\s*\n", text)
    return "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip())
