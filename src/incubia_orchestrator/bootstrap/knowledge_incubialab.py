"""Explicit composition of read-only RAG IncubiaLab retrieval over Neon.

The caller supplies the evaluated embedding; the trusted deployment and the
runtime DSN come from configuration and fail closed. Pools open lazily, so
composing never connects.
"""
from collections.abc import Mapping
from pathlib import Path

from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding
from incubia_orchestrator.modules.knowledge.adapters.pool import KnowledgePools
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge
from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import knowledge_runtime_resolver
from incubia_orchestrator.modules.knowledge.ports import EmbeddingPort

DEPLOYMENT_ENV_VAR = "INCUBIA_KNOWLEDGE_DEPLOYMENT_ID"
BUDGET_ENV_VAR = "INCUBIA_KNOWLEDGE_EMBEDDING_BUDGET_FILE"
# Approved 2026-10-24 for RAG IncubiaLab ingestion and evaluation: USD 1 / 500 calls.
APPROVED_MAX_CALLS = 500
APPROVED_USD_CAP = 1.0
# The ledger reserves UTF-8 bytes as a token bound; the USD cap is the binding limit.
APPROVED_MAX_INPUT_TOKENS = 50_000_000


def openai_embedding_from_env(env: Mapping[str, str], *, metrics=None) -> OpenAIEmbedding:
    """OpenAI ``text-embedding-3-small`` (384) behind the durable approved budget ledger."""
    api_key = env.get("OPENAI_API_KEY", "")
    if not api_key or "REPLACE" in api_key:
        raise ValueError("OPENAI_API_KEY is required for the OpenAI Knowledge embedding")
    path = Path(env.get(BUDGET_ENV_VAR) or
                Path.home() / ".local/state/incubia/knowledge-embedding-budget.sqlite").expanduser()
    budget = EmbeddingBudget(path, max_calls=APPROVED_MAX_CALLS, max_input_tokens=APPROVED_MAX_INPUT_TOKENS,
                             usd_cap=APPROVED_USD_CAP)
    return OpenAIEmbedding(api_key, budget, metrics=metrics)


def compose_incubialab_retrieval(env: Mapping[str, str], embedding: EmbeddingPort, *,
                                 pool_max: int = 4, metrics=None) -> PostgresKnowledge:
    resolve = knowledge_runtime_resolver(env, deployment_id=env.get(DEPLOYMENT_ENV_VAR, ""))
    return PostgresKnowledge(resolve, embedding,
                             pools=KnowledgePools(resolve, max_size=pool_max, metrics=metrics))
