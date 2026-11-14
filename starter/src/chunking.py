"""Fixed-size and structure-aware chunking. Chunks never cross a chapter (page)."""
import re
from .models import Chunk, DocumentPage

# Sentence end: terminal punctuation, optional closing quotes/brackets, then whitespace.
SENTENCE_END = re.compile(r"[.!?…][”’\"')\]]*\s+")


def _chunk(page: DocumentPage, kind: str, i: int, start: int, end: int) -> Chunk:
    meta = {**page.metadata, "char_start": start, "char_end": end}
    return Chunk(f"{page.metadata['unit_id']}:{kind}{i:04d}", page.document_id, page.source,
                 page.page, page.text[start:end].strip(), meta)


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Character windows of `size`, each starting `size - overlap` after the previous."""
    if not 0 <= overlap < size:
        raise ValueError("need 0 <= overlap < size")
    starts = range(0, max(len(page.text) - overlap, 1), size - overlap) if page.text else []
    return [_chunk(page, "f", i, s, min(s + size, len(page.text))) for i, s in enumerate(starts)]


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Greedily group whole paragraphs up to `max_size` chars.

    A paragraph longer than `max_size` is split on sentence ends; a single sentence
    longer than that is hard-cut. Chunk text is an exact slice of the page text.
    """
    text, spans = page.text, []
    for m in re.finditer(r"[^\n]+", text):  # normalized text: paragraphs joined by "\n\n"
        s, e = m.span()
        if e - s <= max_size:
            spans.append((s, e))
            continue
        cuts = [s, *(s + x.end() for x in SENTENCE_END.finditer(m.group())), e]
        for a, b in zip(cuts, cuts[1:]):
            spans += [(i, min(i + max_size, b)) for i in range(a, b, max_size)]

    groups: list[tuple[int, int]] = []
    for s, e in spans:
        if groups and e - groups[-1][0] <= max_size:
            groups[-1] = (groups[-1][0], e)
        else:
            groups.append((s, e))
    return [_chunk(page, "p", i, s, e) for i, (s, e) in enumerate(groups)]
