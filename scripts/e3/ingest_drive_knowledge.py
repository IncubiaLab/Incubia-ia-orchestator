"""Ingest the RAG IncubiaLab Drive folder into the isolated Neon Knowledge branch.

Modes (env from deploy/knowledge-neon.env overlaid by .env; nothing secret printed):
  default           dry-run: Drive inventory + Markdown export + chunk counts. No OpenAI, no Neon.
  --apply           also embed with OpenAI (approved budget) and publish one atomic generation
                    with the ingestor role. Requires --acl-reviewed.
  --query TEXT      retrieve top-k through the read-only runtime role with the same embedding.

Required: INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE (0600 JSON key outside the repo),
INCUBIA_DRIVE_ROOT_FOLDER_ID, INCUBIA_KNOWLEDGE_DEPLOYMENT_ID, INCUBIA_KNOWLEDGE_NEON_BRANCH;
--apply/--query also need OPENAI_API_KEY and the ingest/runtime DSNs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from incubia_orchestrator.bootstrap.knowledge_incubialab import (  # noqa: E402
    DEPLOYMENT_ENV_VAR, compose_incubialab_retrieval, openai_embedding_from_env)
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope  # noqa: E402
from incubia_orchestrator.modules.knowledge.adapters.drive_catalog import DriveSourceCatalog  # noqa: E402
from incubia_orchestrator.modules.knowledge.adapters.drive_http import (  # noqa: E402
    HttpDriveTransport, ServiceAccountDriveIdentity)
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge  # noqa: E402
from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import knowledge_ingest_resolver  # noqa: E402
from incubia_orchestrator.modules.knowledge.application.drive_ingest import ingest_drive_root  # noqa: E402
from incubia_orchestrator.modules.knowledge.domain import RetrievalQuery, SourceCatalogError  # noqa: E402
from scripts.e3.migrate_knowledge import EXPECTED_BRANCH, load_env_file  # noqa: E402
from scripts.e3.neon_branch_guard import require_isolated_branch  # noqa: E402


class ConfigError(ValueError):
    pass


def drive_config(env: Mapping[str, str]) -> tuple[Path, str, str]:
    """Validate the Drive/deployment configuration; returns (key path, root id, deployment)."""
    try:
        require_isolated_branch(env.get("INCUBIA_KNOWLEDGE_NEON_BRANCH"), expected=EXPECTED_BRANCH)
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    key = env.get("INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE", "")
    root_id = env.get("INCUBIA_DRIVE_ROOT_FOLDER_ID", "")
    deployment = env.get(DEPLOYMENT_ENV_VAR, "")
    if not key or not root_id or not deployment:
        raise ConfigError("INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE, INCUBIA_DRIVE_ROOT_FOLDER_ID and "
                          f"{DEPLOYMENT_ENV_VAR} are required")
    key_path = Path(key).expanduser().resolve()
    if key_path.is_relative_to(ROOT):
        raise ConfigError("The service account key must live outside the repository")
    return key_path, root_id, deployment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, action="append")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acl-reviewed", action="store_true",
                        help="confirm every reader of this deployment may read the whole folder")
    parser.add_argument("--query")
    args = parser.parse_args(argv)
    env: dict[str, str] = {}
    for path in args.env_file or (ROOT / "deploy/knowledge-neon.env", ROOT / ".env"):
        if path.is_file():
            env.update(load_env_file(path))
    try:
        if args.query:
            return _query(env, args.query)
        key_path, root_id, deployment = drive_config(env)
        if args.apply and not args.acl_reviewed:
            raise ConfigError("--apply requires --acl-reviewed")
        identity = ServiceAccountDriveIdentity.from_file(key_path)
        catalog = DriveSourceCatalog(HttpDriveTransport(identity), identity)
        embedding = openai_embedding_from_env(env) if args.apply else None
        repository = (PostgresKnowledge(knowledge_ingest_resolver(env, deployment_id=deployment), embedding)
                      if args.apply else None)
        report = ingest_drive_root(catalog, root_id, embedding, repository, deployment,
                                   acl_reviewed=args.acl_reviewed or not args.apply, dry_run=not args.apply)
    except (ConfigError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except SourceCatalogError as exc:  # domain messages are sanitized by contract
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    mode = "apply" if args.apply else "dry-run"
    print(f"{mode}: documents={report.documents} chunks={report.chunks} "
          f"generation={report.generation_id or '-'} skipped={report.skipped or {}}")
    if args.apply:
        print(f"embedding budget: {embedding._budget.snapshot()}")
    return 0


def _query(env: dict[str, str], text: str) -> int:
    embedding = openai_embedding_from_env(env)
    runtime = compose_incubialab_retrieval(env, embedding)
    try:
        scope = ExecutionScope(env.get(DEPLOYMENT_ENV_VAR, ""), "operator", f"query-{uuid4().hex[:8]}",
                               "operator")
        for rank, hit in enumerate(runtime.retrieve(RetrievalQuery(scope, text, "knowledge.search")), 1):
            preview = " ".join(hit.text.split())[:160]
            print(f"{rank}. score={hit.score:.3f} {hit.source_id} {hit.public_ref}\n   {preview}")
    finally:
        runtime._pools.close()
        embedding.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
