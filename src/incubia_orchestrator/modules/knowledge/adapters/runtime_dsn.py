"""Trusted DSN resolver for the read-only Knowledge runtime role (RAG IncubiaLab).

Reads ``INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL`` (see NEON-KNOWLEDGE-DEV.md) and
binds it to one trusted deployment. Validation is fail-closed and messages never
echo the DSN, host or password.
"""
from __future__ import annotations

from typing import Callable, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

ENV_VAR = "INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL"
RUNTIME_ROLE = "incubia_kb_runtime"


class KnowledgeDsnError(ValueError):
    pass


def _validate(dsn: str) -> None:
    parts = urlsplit(dsn)
    host = parts.hostname or ""
    if (parts.scheme not in {"postgres", "postgresql"}
            or not host.endswith(".neon.tech")
            or "-pooler." not in host
            or unquote(parts.username or "") != RUNTIME_ROLE
            or not parts.password or "REPLACE" in dsn
            or not parts.path.lstrip("/")
            or parse_qs(parts.query).get("sslmode") != ["require"]):
        raise KnowledgeDsnError(
            f"{ENV_VAR} must be a pooled TLS Neon DSN for role {RUNTIME_ROLE}")


def knowledge_runtime_resolver(env: Mapping[str, str], *,
                               deployment_id: str) -> Callable[[str], str]:
    """Return ``resolve_dsn`` for ``KnowledgePools``/``PostgresKnowledge``.

    Any deployment other than ``deployment_id`` resolves to ``""``, which the
    Knowledge adapters treat as a deny.
    """
    if not deployment_id:
        raise KnowledgeDsnError("Trusted deployment ID required")
    dsn = env.get(ENV_VAR, "")
    _validate(dsn)
    return lambda requested: dsn if requested == deployment_id else ""
