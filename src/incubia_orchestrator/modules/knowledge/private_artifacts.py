"""Containment checks for private, non-ingestible knowledge artifacts.

RAG-V1 offline bundles (and anything else that is not yet ingestion-ready)
must never be written inside the Git working tree: they are reviewer-only
material and must not be picked up by the sync/ingest pipeline or committed
by accident. This module centralizes that containment check plus the
restrictive filesystem modes every writer of such bundles must use.
"""
from __future__ import annotations

from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


class PrivateArtifactPathError(ValueError):
    """Raised when a candidate directory is not a safe private-artifact location."""


def resolve_private_artifact_dir(path: Path, *, repo_root: Path) -> Path:
    """Resolve ``path`` and reject it if it falls inside ``repo_root``.

    Both paths are resolved (symlinks included) before comparison so that a
    symlink cannot be used to smuggle a private bundle into the working tree.
    Does not create or touch anything on disk.
    """
    resolved = Path(path).resolve()
    resolved_root = Path(repo_root).resolve()
    if resolved == resolved_root or resolved_root in resolved.parents:
        raise PrivateArtifactPathError(
            "output directory must be outside the repository working tree"
        )
    return resolved
