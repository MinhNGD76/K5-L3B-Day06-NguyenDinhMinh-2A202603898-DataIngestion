"""Real embedding provider: OpenRouter's OpenAI-compatible /embeddings endpoint."""
import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """OpenRouter embeddings. Raises on any API failure; never falls back to mock vectors.

    text-embedding-3-* models are symmetric: queries and documents are embedded the
    same way, with no instruction prefix.
    """

    def __init__(self, model_name: str, api_key: str | None = None, batch_size: int = 100) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in starter/.env")
        self.batch_size = batch_size
        self.usage = {"requests": 0, "prompt_tokens": 0, "cost_usd": 0.0}
        self.dimensions = len(self._post(["dimension probe"])[0])

    def _post(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model_name, "input": texts}).encode()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(4):
            try:
                req = urllib.request.Request(OPENROUTER_URL, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.load(resp)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f"embedding API HTTP {e.code}: {e.read()[:300]!r}") from e
            except urllib.error.URLError as e:
                if attempt == 3:
                    raise RuntimeError(f"embedding API unreachable: {e.reason}") from e
            time.sleep(2 ** attempt)
        if "data" not in body:
            raise RuntimeError(f"embedding API error: {body.get('error', body)}")
        data = sorted(body["data"], key=lambda d: d["index"])
        if len(data) != len(texts):
            raise RuntimeError(f"embedding API returned {len(data)} vectors for {len(texts)} texts")
        usage = body.get("usage", {})
        self.usage["requests"] += 1
        self.usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.usage["cost_usd"] += usage.get("cost", 0.0)
        return [d["embedding"] for d in data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors += self._post(texts[i:i + self.batch_size])
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self._post([question])[0]
