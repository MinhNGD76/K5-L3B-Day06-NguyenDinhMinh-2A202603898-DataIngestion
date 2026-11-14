"""Day 06 pipeline. Run from starter/:

    python -m src.run ingest        # chunk + embed + store indexes A and B (re-run safe)
    python -m src.run eval dev      # top-3 traces + metrics for the dev split
    python -m src.run eval test     # only after the strategy is fixed on dev
"""
import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_chapters
from .store import PgVectorStore

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
CORPUS = STARTER / "data" / "The Brothers Karamazov.txt"
DOCUMENT_ID = "karamazov-pg28054"
RESULTS = ROOT / "results"

INDEXES = {  # index name -> chunker; C reuses index B
    "A": lambda page: fixed_size(page, size=500, overlap=50),
    "B": lambda page: by_paragraph(page, max_size=500),
}
STRATEGIES = {"A": ("A", False), "B": ("B", False), "C": ("B", True)}  # name -> (index, use filter)


def _setup() -> tuple[MyEmbedder, PgVectorStore]:
    load_dotenv(STARTER / ".env")
    model, url = os.getenv("EMBEDDING_MODEL"), os.getenv("DATABASE_URL")
    if not model or not url:
        raise SystemExit("Set EMBEDDING_MODEL and DATABASE_URL in starter/.env")
    embedder = MyEmbedder(model)
    store = PgVectorStore(url, embedder.dimensions)
    store.create_schema()
    return embedder, store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ingest() -> None:
    embedder, store = _setup()
    pages = load_chapters(CORPUS, DOCUMENT_ID, CORPUS.relative_to(ROOT).as_posix())
    if len(pages) < 30:
        raise SystemExit(f"only {len(pages)} content units; need >= 30")
    RESULTS.mkdir(exist_ok=True)
    for name, chunker in INDEXES.items():
        t0, usage0 = time.perf_counter(), dict(embedder.usage)
        chunks = [c for p in pages for c in chunker(p)]
        vectors = embedder.embed_documents([c.text for c in chunks])
        store.upsert(name, chunks, vectors)
        stored = store.count(name)
        lengths = [len(c.text) for c in chunks]
        stats = {
            "at": _now(), "index": name, "model": embedder.model_name,
            "dimensions": embedder.dimensions, "units": len(pages), "chunks": len(chunks),
            "rows_in_db": stored, "duplicates_or_stale": stored - len(chunks),
            "chars_total": sum(lengths), "len_min": min(lengths),
            "len_median": statistics.median(lengths), "len_mean": round(statistics.mean(lengths), 1),
            "len_max": max(lengths),
            "embed_tokens": embedder.usage["prompt_tokens"] - usage0["prompt_tokens"],
            "embed_cost_usd": round(embedder.usage["cost_usd"] - usage0["cost_usd"], 6),
            "seconds": round(time.perf_counter() - t0, 1),
        }
        if stored != len(chunks):
            raise SystemExit(f"index {name}: {stored} rows in DB but {len(chunks)} chunks: {stats}")
        with (RESULTS / "ingest_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(stats) + "\n")
        print(stats)


def evaluate(split: str) -> None:
    embedder, store = _setup()
    questions = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    questions = [q for q in questions if q["split"] == split]
    if missing := [i for i in INDEXES if store.count(i) == 0]:
        raise SystemExit(f"indexes {missing} are empty; run `python -m src.run ingest` first")
    query_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in questions}  # shared by A/B/C
    traces = []
    for strategy, (index, use_filter) in STRATEGIES.items():
        for q in questions:
            applied = q["filter"] if use_filter and q["filter"] else None
            hits = store.search(index, query_vectors[q["id"]], top_k=3, filters=applied)
            traces.append({"strategy": strategy, "index": index, "applied_filter": applied,
                           **evaluate_query(q, hits)})
    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / f"traces_{split}.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(t, ensure_ascii=False) + "\n" for t in traces)
    metrics = {"at": _now(), "split": split, "model": embedder.model_name,
               "dimensions": embedder.dimensions, "metric": "cosine, exact (no ANN index)",
               "query_cost_usd": round(embedder.usage["cost_usd"], 6),
               "summary": summarize(traces)}
    (RESULTS / f"metrics_{split}.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    for key, s in metrics["summary"].items():
        flt = f"filter_ok {s['filter_ok']}/{s['filter_questions']}" if s["filter_questions"] else "filter N/A"
        print(f"{key:8} Hit@1 {s['hit_at_1']}/{s['N']}  Hit@3 {s['hit_at_3']}/{s['N']}  "
              f"gold_page@3 {s['gold_page_at_3']}/{s['N']}  {flt}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    sub.add_parser("eval").add_argument("split", choices=["dev", "test"])
    args = parser.parse_args()
    ingest() if args.cmd == "ingest" else evaluate(args.split)


if __name__ == "__main__":
    main()
