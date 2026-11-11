"""Pinned local multilingual embedding for low-latency H4 retrieval."""
from collections.abc import Sequence
from pathlib import Path


class LocalMultilingualEmbedding:
    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    model_version = "qdrant-paraphrase-multilingual-MiniLM-L12-v2-onnx-Q@faf4aa4225822f3bc6376869cb1164e8e3feedd0"
    dimension = 384

    def __init__(self, cache_dir: Path):
        from fastembed import TextEmbedding

        reference = (cache_dir / "models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
                     / "refs/main")
        expected = self.model_version.rsplit("@", 1)[-1]
        if not reference.exists() or reference.read_text().strip() != expected:
            raise RuntimeError("Pinned local embedding model is not available in cache")
        self._model = TextEmbedding(model_name=self.model_name, cache_dir=str(cache_dir),
                                    threads=2, providers=["CPUExecutionProvider"])

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Non-empty embedding texts required")
        vectors = tuple(tuple(float(value) for value in vector) for vector in self._model.embed(list(texts)))
        if len(vectors) != len(texts) or any(len(vector) != self.dimension for vector in vectors):
            raise RuntimeError("Local embedding returned wrong shape")
        return vectors
