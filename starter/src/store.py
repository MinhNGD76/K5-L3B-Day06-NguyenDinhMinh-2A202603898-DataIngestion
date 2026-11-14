"""Store and search vectors using PostgreSQL + pgvector (exact cosine search, no ANN index)."""
import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import Chunk

FILTER_COLUMNS = {"book", "part"}  # whitelist: only these become SQL identifiers


def _vec(v: list[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_schema(self) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT atttypmod AS dims FROM pg_attribute "
                "WHERE attrelid = to_regclass('chunks') AND attname = 'embedding'").fetchone()
            if row and row["dims"] != self.dimensions:
                raise RuntimeError(f"table chunks has vector({row['dims']}), model gives "
                                   f"{self.dimensions}; use a new table or drop it deliberately")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    strategy    text NOT NULL,
                    chunk_id    text NOT NULL,
                    document_id text NOT NULL,
                    source      text NOT NULL,
                    page        int  NOT NULL,
                    part        text,
                    book        text,
                    text        text NOT NULL,
                    metadata    jsonb NOT NULL,
                    embedding   vector({self.dimensions}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id))""")
            conn.execute("CREATE INDEX IF NOT EXISTS chunks_strategy_book ON chunks (strategy, book)")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Insert or update by (strategy, chunk_id), then delete this strategy's chunks of
        the same documents that are no longer produced (changed source / chunking)."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if bad := [c.chunk_id for c, v in zip(chunks, vectors) if len(v) != self.dimensions]:
            raise ValueError(f"wrong vector dimensions for {bad[:3]}")
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("duplicate chunk_id in batch")
        rows = [(strategy, c.chunk_id, c.document_id, c.source, c.page, c.metadata.get("part"),
                 c.metadata.get("book"), c.text, json.dumps(c.metadata, ensure_ascii=False), _vec(v))
                for c, v in zip(chunks, vectors)]
        with self._connect() as conn, conn.cursor() as cur:  # one transaction
            cur.executemany("""
                INSERT INTO chunks (strategy, chunk_id, document_id, source, page, part, book,
                                    text, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                    document_id = EXCLUDED.document_id, source = EXCLUDED.source,
                    page = EXCLUDED.page, part = EXCLUDED.part, book = EXCLUDED.book,
                    text = EXCLUDED.text, metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding""", rows)
            cur.execute("DELETE FROM chunks WHERE strategy = %s AND document_id = ANY(%s) "
                        "AND NOT chunk_id = ANY(%s)",
                        (strategy, list({c.document_id for c in chunks}), [c.chunk_id for c in chunks]))

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT count(*) AS n FROM chunks WHERE strategy = %s",
                                (strategy,)).fetchone()["n"]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if len(query_vector) != self.dimensions:
            raise ValueError("query vector has wrong dimensions")
        if unknown := set(filters or {}) - FILTER_COLUMNS:
            raise ValueError(f"unsupported filter fields: {sorted(unknown)}")
        where = "".join(f" AND {k} = %s" for k in (filters or {}))
        q = _vec(query_vector)
        with self._connect() as conn:
            return conn.execute(
                f"SELECT chunk_id, document_id, source, page, part, book, text, metadata, "
                f"1 - (embedding <=> %s::vector) AS score FROM chunks "
                f"WHERE strategy = %s{where} ORDER BY embedding <=> %s::vector LIMIT %s",
                (q, strategy, *(filters or {}).values(), q, top_k)).fetchall()
