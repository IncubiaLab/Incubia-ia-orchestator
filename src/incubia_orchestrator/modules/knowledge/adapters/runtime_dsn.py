"""Trusted DSN resolvers for the RAG IncubiaLab Knowledge roles.

``INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL`` (read-only) and
``INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL`` (DML) are documented in
NEON-KNOWLEDGE-DEV.md. Each is bound to one trusted deployment. Validation is
fail-closed and messages never echo the DSN, host or password.
"""
from __future__ import annotations

from typing import Callable, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

ENV_VAR = "INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL"
RUNTIME_ROLE = "incubia_kb_runtime"
INGEST_ENV_VAR = "INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL"
INGEST_ROLE = "incubia_kb_ingestor"


class KnowledgeDsnError(ValueError):
    pass


def _validate(dsn: str, env_var: str, role: str) -> None:
    parts = urlsplit(dsn)
    host = parts.hostname or ""
    if (parts.scheme not in {"postgres", "postgresql"}
            or not host.endswith(".neon.tech")
            or "-pooler." not in host
            or unquote(parts.username or "") != role
            or not parts.password or "REPLACE" in dsn
            or not parts.path.lstrip("/")
            or parse_qs(parts.query).get("sslmode") != ["require"]):
        raise KnowledgeDsnError(f"{env_var} must be a pooled TLS Neon DSN for role {role}")


def _resolver(env: Mapping[str, str], deployment_id: str, env_var: str,
              role: str) -> Callable[[str], str]:
    if not deployment_id:
        raise KnowledgeDsnError("Trusted deployment ID required")
    dsn = env.get(env_var, "")
    _validate(dsn, env_var, role)
    return lambda requested: dsn if requested == deployment_id else ""


def knowledge_runtime_resolver(env: Mapping[str, str], *,
                               deployment_id: str) -> Callable[[str], str]:
    """Return ``resolve_dsn`` for ``KnowledgePools``/``PostgresKnowledge``.

    Any deployment other than ``deployment_id`` resolves to ``""``, which the
    Knowledge adapters treat as a deny.
    """
    return _resolver(env, deployment_id, ENV_VAR, RUNTIME_ROLE)


def knowledge_ingest_resolver(env: Mapping[str, str], *,
                              deployment_id: str) -> Callable[[str], str]:
    """Same contract as the runtime resolver, for the ingestor (publish/revoke)."""
    return _resolver(env, deployment_id, INGEST_ENV_VAR, INGEST_ROLE)
