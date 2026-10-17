"""Budgeted OpenAI embedding adapter for the explicitly approved H4 campaign."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Sequence

import httpx


class EmbeddingBudget:
    """Durable fail-closed reservation ledger, separate from E2 counters."""

    def __init__(self, path: Path, *, max_calls: int, max_input_tokens: int,
                 usd_cap: float, usd_per_million_tokens: float = 0.02):
        if max_calls <= 0 or max_input_tokens <= 0 or usd_cap <= 0:
            raise ValueError("Positive budget limits are required")
        self.path = path
        self.max_calls, self.max_input_tokens = max_calls, max_input_tokens
        self.usd_cap, self.rate = usd_cap, usd_per_million_tokens
        self._lock = Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "calls INTEGER NOT NULL, reserved_tokens INTEGER NOT NULL, "
                       "actual_tokens INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO budget VALUES (1,0,0,0)")

    def reserve(self, texts: Sequence[str]) -> None:
        # UTF-8 bytes bound the token count conservatively for the accepted corpus.
        reserved = sum(len(text.encode("utf-8")) for text in texts)
        if not reserved:
            raise ValueError("Empty embedding request")
        with self._lock, sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            calls, tokens, _ = db.execute("SELECT calls,reserved_tokens,actual_tokens FROM budget WHERE id=1").fetchone()
            next_tokens = tokens + reserved
            if calls + 1 > self.max_calls or next_tokens > self.max_input_tokens or (
                next_tokens * self.rate / 1_000_000 > self.usd_cap
            ):
                raise RuntimeError("Embedding campaign budget exhausted")
            db.execute("UPDATE budget SET calls=?, reserved_tokens=? WHERE id=1", (calls + 1, next_tokens))

    def record(self, actual_tokens: int) -> None:
        if actual_tokens < 0:
            raise ValueError("Negative usage")
        with self._lock, sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE budget SET actual_tokens=actual_tokens+? WHERE id=1", (actual_tokens,))

    def snapshot(self) -> dict:
        with sqlite3.connect(self.path) as db:
            calls, reserved, actual = db.execute(
                "SELECT calls,reserved_tokens,actual_tokens FROM budget WHERE id=1").fetchone()
        return {"calls": calls, "reserved_tokens": reserved, "actual_tokens": actual,
                "estimated_usd": round(actual * self.rate / 1_000_000, 8)}


class OpenAIEmbedding:
    model_version = "text-embedding-3-small:384:e3-h4-v1"
    dimension = 384

    def __init__(self, api_key: str, budget: EmbeddingBudget, *, client: httpx.Client | None = None):
        if not api_key:
            raise ValueError("API key required")
        self._api_key, self._budget = api_key, budget
        self._client = client or httpx.Client(timeout=10)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not isinstance(text, str) or not text.strip() or
                            len(text.encode("utf-8")) > 8192 for text in texts):
            raise ValueError("Invalid embedding batch")
        self._budget.reserve(texts)
        try:
            response = self._client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "dimensions": 384,
                      "encoding_format": "float", "input": list(texts)},
            )
            response.raise_for_status()
            body = response.json()
            usage = body.get("usage", {}).get("total_tokens")
            if not isinstance(usage, int) or usage < 0:
                raise RuntimeError("Embedding response omitted usage")
            self._budget.record(usage)
            data = sorted(body.get("data", ()), key=lambda row: row["index"])
            if len(data) != len(texts):
                raise RuntimeError("Embedding batch length mismatch")
            vectors = tuple(tuple(float(value) for value in row["embedding"]) for row in data)
            if any(len(vector) != self.dimension for vector in vectors):
                raise RuntimeError("Embedding dimension mismatch")
            return vectors
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Embedding request failed") from None
