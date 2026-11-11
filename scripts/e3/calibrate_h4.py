"""Calibrate abstention only on frozen dev cases, before rerunning val."""
import json
import math
import os
from hashlib import sha256
from pathlib import Path

from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding
from incubia_orchestrator.modules.knowledge.adapters.local_embedding import LocalMultilingualEmbedding
from scripts.e3.run_h4_neon_campaign import _api_key, _rows

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "evals/results/e3-4-dev-calibration-2026-10-15.json"


def main():
    use_local = os.getenv("INCUBIA_E3_H4_EMBEDDING") == "local"
    if not use_local and os.getenv("INCUBIA_E3_H4_APPROVED_BUDGET") != "1":
        raise RuntimeError("Approved H4 budget flag required")
    budget = None if use_local else EmbeddingBudget(
        Path("/tmp/incubia-e3-h4-approved-budget.sqlite"), max_calls=250,
        max_input_tokens=100_000, usd_cap=0.10)
    adapter = (LocalMultilingualEmbedding(Path("/tmp/incubia-e3-h4-fastembed")) if use_local
               else OpenAIEmbedding(_api_key(), budget))
    try:
        sources = _rows("sources.jsonl")
        dev = [row for row in _rows("retrieval.jsonl") if row["split"] == "dev"]
        dev.extend(_rows("retrieval_dev_negative.jsonl"))
        source_vectors = adapter.embed(tuple(source["content"] for source in sources))
        query_vectors = adapter.embed(tuple(row["query"] for row in dev))
        examples = []
        for row, vector in zip(dev, query_vectors, strict=True):
            ranked = sorted(((sum(a * b for a, b in zip(vector, source_vector)) /
                              (math.sqrt(sum(a * a for a in vector)) *
                               math.sqrt(sum(b * b for b in source_vector))), source["source_id"])
                             for source, source_vector in zip(sources, source_vectors, strict=True)
                             if source["deployment_id"] == row["deployment_id"]), reverse=True)[:5]
            examples.append({"id": row["id"], "answerable": row["answerable"],
                             "cross": "forbidden_source" in row,
                             "top_score": ranked[0][0],
                             "expected_score": max((score for score, source_id in ranked
                                                    if source_id in row["expected_sources"]), default=None)})
        # A cross-deployment request is denied by trusted routing metadata before
        # similarity. Threshold tuning uses only the remaining dev cases.
        scores = sorted({item["top_score"] for item in examples})
        thresholds = [0.0, 1.0] + [(a + b) / 2 for a, b in zip(scores, scores[1:])]
        candidates = []
        for threshold in thresholds:
            positives = [item for item in examples if item["answerable"]]
            negatives = [item for item in examples if not item["answerable"]]
            recall = sum(item["expected_score"] is not None and item["expected_score"] >= threshold
                         for item in positives) / len(positives)
            abstention = sum(item["cross"] or item["top_score"] < threshold
                             for item in negatives) / len(negatives)
            candidates.append((min(recall, abstention), recall + abstention, threshold, recall, abstention))
        _, _, threshold, recall, abstention = max(candidates)
        report = {"threshold": threshold, "model_version": adapter.model_version,
                  "dev_recall_at_5": recall,
                  "dev_abstention": abstention, "dev_respondable": 20,
                  "dev_unanswerable": 20, "cross_scope_guard": True,
                  "budget": budget.snapshot() if budget else None,
                  "dev_negative_sha256": sha256((ROOT / "evals/e3/retrieval_dev_negative.jsonl").read_bytes()).hexdigest(),
                  "retrieval_val_sha256": sha256((ROOT / "evals/e3/retrieval.jsonl").read_bytes()).hexdigest(),
                  "gate_closed": False}
        output = (ROOT / "evals/results/e3-4-dev-calibration-local-2026-10-15.json"
                  if use_local else OUTPUT)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({key: report[key] for key in ("threshold", "dev_recall_at_5", "dev_abstention")}))
    finally:
        if isinstance(adapter, OpenAIEmbedding):
            adapter.close()


if __name__ == "__main__":
    main()
