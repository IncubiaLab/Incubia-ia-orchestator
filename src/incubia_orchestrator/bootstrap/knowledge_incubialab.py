"""Explicit composition of read-only RAG IncubiaLab retrieval over Neon.

The caller supplies the evaluated embedding; the trusted deployment and the
runtime DSN come from configuration and fail closed. Pools open lazily, so
composing never connects.
"""
from collections.abc import Mapping

from incubia_orchestrator.modules.knowledge.adapters.pool import KnowledgePools
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge
from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import knowledge_runtime_resolver
from incubia_orchestrator.modules.knowledge.ports import EmbeddingPort

DEPLOYMENT_ENV_VAR = "INCUBIA_KNOWLEDGE_DEPLOYMENT_ID"


def compose_incubialab_retrieval(env: Mapping[str, str], embedding: EmbeddingPort, *,
                                 pool_max: int = 4, metrics=None) -> PostgresKnowledge:
    resolve = knowledge_runtime_resolver(env, deployment_id=env.get(DEPLOYMENT_ENV_VAR, ""))
    return PostgresKnowledge(resolve, embedding,
                             pools=KnowledgePools(resolve, max_size=pool_max, metrics=metrics))
