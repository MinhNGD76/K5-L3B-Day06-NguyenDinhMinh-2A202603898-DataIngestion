"""Offline checks for chunking and evaluation. Run from starter/: python -m tests.test_pipeline"""
from src.chunking import by_paragraph, fixed_size
from src.evaluation import evaluate_query, summarize
from src.models import DocumentPage

META = {"unit_id": "BI-CI", "book": "Book I", "part": "Part I"}
PARAS = ["Short one.", "A second paragraph that is a bit longer.",
         "Sentence one is here. Sentence two follows! Is three a question? " * 4]
PAGE = DocumentPage("doc", "src.txt", 1, "\n\n".join(PARAS), META)


def test_fixed_size_covers_text_with_overlap():
    chunks = fixed_size(PAGE, size=60, overlap=10)
    assert all(len(c.text) <= 60 for c in chunks)
    assert chunks[0].metadata["char_start"] == 0 and chunks[-1].metadata["char_end"] == len(PAGE.text)
    for a, b in zip(chunks, chunks[1:]):
        assert b.metadata["char_start"] == a.metadata["char_end"] - 10
    assert chunks[0].page == 1 and chunks[0].metadata["book"] == "Book I"
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_by_paragraph_keeps_short_paragraphs_whole_and_respects_max():
    chunks = by_paragraph(PAGE, max_size=80)
    assert all(len(c.text) <= 80 for c in chunks)
    # greedy: two whole paragraphs, plus the next sentence because it still fits in 80
    assert chunks[0].text == "Short one.\n\nA second paragraph that is a bit longer.\n\nSentence one is here."
    assert all(c.text in PAGE.text for c in chunks)  # exact slices, nothing rewritten
    # long paragraph split on sentence ends, not mid-word
    assert all(c.text.endswith(("?", "!", ".")) for c in chunks)
    joined = " ".join(c.text for c in chunks).split()
    assert joined == PAGE.text.split()  # every word kept, in order, once


def test_by_paragraph_hard_cuts_oversized_sentence():
    page = DocumentPage("doc", "s", 2, "x" * 250, META)
    assert [len(c.text) for c in by_paragraph(page, max_size=100)] == [100, 100, 50]


def _hit(page, text, book="Book I"):
    return {"chunk_id": "c", "document_id": "doc", "page": page, "book": book,
            "text": text, "score": 0.5, "metadata": {"unit_id": "u"}}


def test_evaluate_query_hits_alt_evidence_and_filter():
    q = {"id": "q", "split": "dev", "type": "filter", "question": "?", "gold_source_id": "doc",
         "gold_page": 1, "evidence_quote": "the brass pestle", "filter": {"book": "Book I"},
         "alt_evidence": [{"page": 2, "quote": "a pestle"}]}
    t = evaluate_query(q, [_hit(1, "nothing"), _hit(2, "saw a pestle there"), _hit(1, "the brass")])
    assert (t["hit_at_1"], t["hit_at_3"], t["first_hit_rank"]) == (False, True, 2)
    assert t["gold_page_at_3"] and t["filter_ok"]
    t = evaluate_query(q, [_hit(1, "the brass pestle", book="Book V")])
    assert t["hit_at_1"] and t["filter_ok"] is False
    t = evaluate_query({**q, "filter": None}, [_hit(3, "the brass pestle")])  # wrong page
    assert not t["hit_at_3"] and t["filter_ok"] is None


def test_summarize_counts():
    traces = [{"strategy": "A", "split": "dev", "hit_at_1": True, "hit_at_3": True,
               "gold_page_at_3": True, "filter": None, "filter_ok": None},
              {"strategy": "A", "split": "dev", "hit_at_1": False, "hit_at_3": True,
               "gold_page_at_3": True, "filter": {"book": "Book I"}, "filter_ok": False}]
    s = summarize(traces)["A/dev"]
    assert (s["N"], s["hit_at_1"], s["hit_at_3"], s["filter_questions"], s["filter_ok"]) == (2, 1, 2, 1, 0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
