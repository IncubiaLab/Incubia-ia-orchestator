"""Guard every RAG-V1 / E3 Neon campaign against a shared or production branch.

The user supplied the branch name `production` for RAG-V1 offline work. That
branch (and every other shared/default Neon branch) must be structurally
impossible to target: this module is the single place that decides whether a
branch name is a safe, dedicated, isolated campaign branch, and the single
place that turns a DSN into a sanitized, non-secret identity for logging.

Pure and importable: no network call, no subprocess, no credential file
access, at import time or otherwise.
"""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Mapping
from urllib.parse import unquote, urlsplit

PROHIBITED_BRANCHES = frozenset({"production", "prod", "main", "master", "default"})

_SAFE_BRANCH_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_NEON_HOST_SUFFIX = ".neon.tech"
_POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})


class BranchGuardError(ValueError):
    """Raised when a Neon branch/DSN fails the RAG-V1 isolation guard."""


def require_isolated_branch(name: str | None, *, expected: str | None = None) -> str:
    """Return ``name`` normalised, or raise if it is not a safe isolated branch.

    Rejects missing names, shared/production names (case/whitespace
    insensitively), names that are not a safe branch slug, and names that
    do not match ``expected`` when one is given. A prohibited name is
    rejected before the ``expected`` comparison runs, so it can never be
    whitelisted by also passing it as ``expected``.
    """
    if name is None:
        raise BranchGuardError("a dedicated isolated Neon branch must be named explicitly")
    stripped = name.strip()
    if not stripped:
        raise BranchGuardError("a dedicated isolated Neon branch must be named explicitly")
    normalized = stripped.lower()
    if normalized in PROHIBITED_BRANCHES:
        raise BranchGuardError(
            "refusing a shared/production Neon branch; a dedicated isolated branch is required"
        )
    if not _SAFE_BRANCH_RE.match(normalized):
        raise BranchGuardError("branch name is not a safe isolated branch slug")
    if expected is not None and normalized != expected.strip().lower():
        raise BranchGuardError("branch does not match the expected isolated campaign branch")
    return normalized


def guard_campaign_environment(
    env: Mapping[str, str],
    *,
    expected_branch: str,
    authorization_flag: str = "INCUBIA_E3_NEON_TESTS",
) -> str:
    """Validate an injected environment mapping for an opt-in Neon campaign.

    Requires explicit authorization (``env[authorization_flag] == "1"``) and
    a branch name that passes :func:`require_isolated_branch` against
    ``expected_branch``. Returns the validated branch name.
    """
    if env.get(authorization_flag) != "1":
        raise BranchGuardError(f"set {authorization_flag}=1 to authorize the Neon campaign")
    return require_isolated_branch(env.get("INCUBIA_E3_NEON_BRANCH"), expected=expected_branch)


def sanitize_dsn_reference(dsn: str) -> str:
    """Return a non-secret ``<scheme>://<user>@<host-digest>/<database>`` identity.

    Drops the password, the query string, and the port; replaces the host
    with a short SHA-256 digest. Raises :class:`BranchGuardError` for a
    non-postgres scheme, for a host that is not a ``*.neon.tech`` Neon
    endpoint, or when a secret appears to be smuggled outside the userinfo
    slot (e.g. into the database/path segment) where it cannot be safely
    excised.
    """
    parts = urlsplit(dsn)
    scheme = parts.scheme.lower()
    if scheme not in _POSTGRES_SCHEMES:
        raise BranchGuardError("DSN must use a postgres:// or postgresql:// scheme")
    host = (parts.hostname or "").lower()
    if not host.endswith(_NEON_HOST_SUFFIX):
        raise BranchGuardError("DSN host must be a Neon (*.neon.tech) endpoint")
    database = (parts.path or "").lstrip("/")
    if not database or not _SAFE_IDENTIFIER_RE.match(database):
        raise BranchGuardError("DSN embeds a secret that cannot be safely removed")
    username = unquote(parts.username or "")
    if not username or not _SAFE_IDENTIFIER_RE.match(username):
        raise BranchGuardError("DSN embeds a secret that cannot be safely removed")
    digest = sha256(host.encode("utf-8")).hexdigest()[:16]
    return f"{scheme}://{username}@{digest}/{database}"
