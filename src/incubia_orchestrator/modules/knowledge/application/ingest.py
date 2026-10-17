"""Build a whole generation before publishing it atomically."""
from collections.abc import Sequence

from incubia_orchestrator.modules.knowledge.domain import Source
from incubia_orchestrator.modules.knowledge.ports import EmbeddingPort, KnowledgeRepository


class IngestKnowledge:
    def __init__(self, repository: KnowledgeRepository, embedding: EmbeddingPort):
        self.repository, self.embedding = repository, embedding

    def __call__(self, deployment_id: str, sources: Sequence[Source]) -> str:
        if not deployment_id or not sources:
            raise ValueError("Deployment and sources are required")
        if any(source.deployment_id != deployment_id or source.revoked for source in sources):
            raise ValueError("Source scope or status is invalid")
        if len({source.source_id for source in sources}) != len(sources):
            raise ValueError("Duplicate source ID")
        vectors = self.embedding.embed([source.content for source in sources])
        if len(vectors) != len(sources) or any(len(vector) != self.embedding.dimension for vector in vectors):
            raise ValueError("Embedding batch has wrong shape")
        return self.repository.publish(deployment_id, sources, vectors, self.embedding.model_version)
