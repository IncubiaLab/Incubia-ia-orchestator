"""Deterministic scoped retrieval for contract and orchestration tests."""
from datetime import datetime, timezone

from incubia_orchestrator.modules.knowledge.domain import EvidenceItem, RetrievalQuery


class FakeRetrieval:
    def __init__(self, items=()):
        self.items = tuple(items)
        self.calls: list[RetrievalQuery] = []

    def retrieve(self, query: RetrievalQuery) -> tuple[EvidenceItem, ...]:
        self.calls.append(query)
        if query.deadline is not None and datetime.now(timezone.utc) >= query.deadline:
            return ()
        words = set(query.text.casefold().split())
        candidates = (item for item in self.items if item.deployment_id == query.scope.deployment_id)
        ranked = sorted(candidates, key=lambda item: (-len(words.intersection(item.text.casefold().split())),
                                                       item.source_id, item.chunk_id))
        return tuple(item for item in ranked if words.intersection(item.text.casefold().split()))[:query.top_k]
