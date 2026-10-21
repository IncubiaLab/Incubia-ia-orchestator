#!/usr/bin/env python3
"""Offline Markdown bundle preparer for RAG-V1 (Task 1 — NOT ingestion).

Turns an already-exported Drive document (plain Markdown/text on local disk)
into a private, human-reviewable bundle of ``document.md`` + ``manifest.json``.
This is strictly an offline, local-filesystem step: it makes no network call,
reads no credentials, and does not touch the knowledge ingestion pipeline,
schema, or database. Every manifest it writes is explicitly marked
``ingest_ready: false`` until a human has completed both the extraction and
ACL review — nothing here validates a real corpus or connects one.

The resulting bundle is written outside the Git working tree only; writing
inside the repository is refused.

Example (offline, no credentials involved)::

    python scripts/e3/prepare_knowledge_markdown.py /path/to/export.md \\
      --output-dir /private/rag-v1-bundles \\
      --deployment-id incubialab --source-id drive:file-1 --source-version v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Tests load this script directly via importlib.util.spec_from_file_location
# without registering it in sys.modules. Python 3.14's dataclasses needs
# sys.modules[cls.__module__] to exist (for postponed-annotation lookups,
# since this file uses `from __future__ import annotations`), so register a
# placeholder entry ourselves; this has no effect under a normal `import`.
if __name__ not in sys.modules:
    import types as _types
    sys.modules[__name__] = _types.ModuleType(__name__)

from incubia_orchestrator.modules.knowledge.private_artifacts import (  # noqa: E402
    DIR_MODE,
    FILE_MODE,
    resolve_private_artifact_dir,
)

CONVERTER_VERSION = "1.0.0"
PIPELINE_VERSION = "rag-v1-offline"
REVIEW_PENDING = "pending"

_ACCEPTED_SUFFIXES = {".md", ".markdown", ".txt"}
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class ConversionError(ValueError):
    """Raised when an input cannot be safely converted in RAG-V1 offline mode."""


def ingest_ready_from_reviews(*, acl_review: str, extraction_review: str) -> bool:
    """A bundle is only ingest-ready once neither review is still pending."""
    return acl_review != REVIEW_PENDING and extraction_review != REVIEW_PENDING


def _slug(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", value).strip("-")
    return cleaned or "x"


def _digest_component(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{_slug(value)[:40]}-{digest}"


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ConversionError("repository root could not be determined")


def _normalize_markdown(raw: bytes) -> bytes:
    data = raw
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


@dataclass(frozen=True)
class _PrepareRequest:
    source: Path
    output_dir: Path
    deployment_id: str
    source_id: str
    source_version: str
    source_url: str | None
    max_bytes: int

    def __post_init__(self) -> None:
        if not all((self.deployment_id.strip(), self.source_id.strip(), self.source_version.strip())):
            raise ConversionError("deployment_id, source_id and source_version are required")
        if self.max_bytes <= 0:
            raise ConversionError("max_bytes must be positive")


def _validate_and_read(source: Path, *, max_bytes: int) -> tuple[bytes, bytes]:
    """Return ``(raw_bytes, markdown_bytes)``; raise ConversionError on any problem."""
    if source.is_symlink() or not source.is_file():
        raise ConversionError("source must be a regular file")

    suffix = source.suffix.lower()
    if suffix not in _ACCEPTED_SUFFIXES:
        raise ConversionError(
            f"conversion for '{suffix or 'files without an extension'}' is not implemented in V1"
        )

    try:
        size = source.stat().st_size
    except OSError as exc:
        raise ConversionError("source could not be read") from exc
    if size > max_bytes:
        raise ConversionError("source exceeds the configured size limit")

    raw = source.read_bytes()
    markdown = _normalize_markdown(raw)
    try:
        text = markdown.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConversionError("source is not valid UTF-8 text") from exc
    if "\x00" in text:
        raise ConversionError("source contains a NUL byte and is not valid text")
    if not text.strip():
        raise ConversionError("source is empty after normalization")

    return raw, markdown


@dataclass(frozen=True)
class _BundlePaths:
    bundle_dir: Path
    document_path: Path
    manifest_path: Path


def _bundle_paths(private_base: Path, *, deployment_id: str, source_id: str,
                   source_version: str) -> _BundlePaths:
    bundle_dir = private_base / _slug(deployment_id) / _digest_component(source_id) / _slug(source_version)
    return _BundlePaths(bundle_dir, bundle_dir / "document.md", bundle_dir / "manifest.json")


def _makedirs_private(path: Path) -> None:
    to_create: list[Path] = []
    current = path
    while not current.exists():
        to_create.append(current)
        current = current.parent
    for directory in reversed(to_create):
        directory.mkdir(mode=DIR_MODE)
        os.chmod(directory, DIR_MODE)


def _write_private_file(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    os.chmod(path, FILE_MODE)


def prepare(source: Path, output_dir: Path, *, deployment_id: str, source_id: str,
            source_version: str, source_url: str | None = None,
            max_bytes: int = 25 * 1024 * 1024) -> Path:
    """Convert ``source`` into a private, reviewable document.md + manifest.json bundle.

    Returns the path to the written manifest.json. Raises ``ConversionError``
    (a ``ValueError`` subclass) and creates nothing on disk if any validation
    fails -- including when the resolved output directory would land inside
    the repository working tree. The resulting bundle is never ingest-ready.
    """
    request = _PrepareRequest(
        source=Path(source), output_dir=Path(output_dir), deployment_id=deployment_id,
        source_id=source_id, source_version=source_version, source_url=source_url,
        max_bytes=max_bytes,
    )

    raw, markdown = _validate_and_read(request.source, max_bytes=request.max_bytes)

    repo_root = _find_repo_root(Path(__file__).resolve())
    private_base = resolve_private_artifact_dir(request.output_dir, repo_root=repo_root)

    paths = _bundle_paths(
        private_base,
        deployment_id=request.deployment_id,
        source_id=request.source_id,
        source_version=request.source_version,
    )

    _makedirs_private(paths.bundle_dir)
    _write_private_file(paths.document_path, markdown)

    acl_review = REVIEW_PENDING
    extraction_review = REVIEW_PENDING
    manifest = {
        "deployment_id": request.deployment_id,
        "source_id": request.source_id,
        "source_version": request.source_version,
        "source_url": request.source_url,
        "converter_version": CONVERTER_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown).hexdigest(),
        "source_bytes": len(raw),
        "markdown_bytes": len(markdown),
        "extraction_review": extraction_review,
        "acl_review": acl_review,
        "ingest_ready": ingest_ready_from_reviews(
            acl_review=acl_review, extraction_review=extraction_review
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_private_file(paths.manifest_path, json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))

    return paths.manifest_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepare_knowledge_markdown.py",
        description="Convert an exported document into a private, reviewable RAG-V1 offline bundle.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        manifest_path = prepare(
            args.input, args.output_dir,
            deployment_id=args.deployment_id,
            source_id=args.source_id,
            source_version=args.source_version,
            source_url=args.source_url,
            max_bytes=args.max_bytes,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(str(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
