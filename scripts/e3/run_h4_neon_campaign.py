"""Opt-in, isolated E3-4 mechanics campaign on the approved Neon branch.

Creates two temporary databases and roles, writes only synthetic data, drops
them in finally, and records quality/latency without claiming gate closure.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.knowledge.adapters.embedding import HashEmbedding
from incubia_orchestrator.modules.knowledge.adapters.openai_embedding import EmbeddingBudget, OpenAIEmbedding
from incubia_orchestrator.modules.knowledge.adapters.local_embedding import LocalMultilingualEmbedding
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge
from incubia_orchestrator.modules.knowledge.adapters.pool import KnowledgePools
from incubia_orchestrator.modules.knowledge.application.ingest import IngestKnowledge
from incubia_orchestrator.modules.knowledge.domain import RetrievalQuery, Source

from scripts.e3.neon_h1 import _run_neon_connection
from scripts.e3.run_h4_g6_review import main as run_g6_review


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals/e3"
RESULTS = ROOT / "evals/results"


class CachedEmbedding:
    """Reuse identical query vectors for exact/HNSW comparison within one run."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.model_version = delegate.model_version
        self.dimension = delegate.dimension
        self._cache = {}

    def embed(self, texts):
        missing = tuple(dict.fromkeys(text for text in texts if text not in self._cache))
        if missing:
            vectors = self.delegate.embed(missing)
            self._cache.update(zip(missing, vectors, strict=True))
        return tuple(self._cache[text] for text in texts)


def _with_database(dsn: str, database: str, role: str, password: str) -> str:
    parsed = urlsplit(dsn)
    host = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, f"{quote(role)}:{quote(password)}@{host}",
                       f"/{database}", parsed.query, ""))


def _rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATASET / name).read_text().splitlines()]


def result_paths(mode: str, started_at: datetime) -> tuple[Path, Path]:
    """Create new evidence paths; never overwrite historical E3-4 results."""
    if mode not in {"hash", "openai", "local"}:
        raise ValueError("Unknown H4 embedding mode")
    label = "local" if mode == "local" else "openai-pooled" if mode == "openai" else "mechanics"
    suffix = started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        RESULTS / f"e3-4-neon-{label}-{suffix}.json",
        RESULTS / f"e3-4-g6-neon-{label}-{suffix}.json",
    )


def _api_key() -> str:
    value = os.getenv("OPENAI_API_KEY", "")
    if value:
        return value
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("OPENAI_API_KEY is not configured")


def main() -> int:
    if os.getenv("INCUBIA_E3_H4_NEON_TESTS") != "1" or os.getenv("INCUBIA_E3_NEON_BRANCH") != "e3-h1-synthetic":
        raise RuntimeError("Explicit H4 opt-in and approved synthetic branch are required")
    owner_dsn = _run_neon_connection("neondb_owner")
    parsed = urlsplit(owner_dsn)
    if parsed.username != "neondb_owner" or parsed.path != "/neondb" or not (parsed.hostname or "").endswith(".neon.tech"):
        raise RuntimeError("Unexpected owner connection")
    suffix = secrets.token_hex(4)
    identities = {label: (f"e3h4_{label}_{suffix}", f"e3h4_{label}_{suffix}", secrets.token_urlsafe(32))
                  for label in ("alpha", "beta")}
    created_databases: list[str] = []
    created_roles: list[str] = []
    mode = os.getenv("INCUBIA_E3_H4_EMBEDDING", "hash")
    if mode not in {"hash", "openai", "local"}:
        raise ValueError("Unknown H4 embedding mode")
    use_api = mode == "openai"
    use_local = mode == "local"
    if use_api and os.getenv("INCUBIA_E3_H4_APPROVED_BUDGET") != "1":
        raise RuntimeError("Explicit approved embedding budget is required")
    budget = (EmbeddingBudget(Path("/tmp/incubia-e3-h4-approved-budget.sqlite"), max_calls=250,
                              max_input_tokens=100_000, usd_cap=0.10) if use_api else None)
    api_embedding = (OpenAIEmbedding(_api_key(), budget) if budget else
                     LocalMultilingualEmbedding(Path("/tmp/incubia-e3-h4-fastembed")) if use_local else
                     HashEmbedding())
    embedding = CachedEmbedding(api_embedding)
    calibration = None
    if use_api or use_local:
        calibration_name = ("e3-4-dev-calibration-local-2026-10-15.json" if use_local
                            else "e3-4-dev-calibration-2026-10-15.json")
        calibration = json.loads((RESULTS / calibration_name).read_text())
        if calibration.get("model_version", embedding.model_version) != embedding.model_version:
            raise RuntimeError("Calibration model differs from campaign model")
        if calibration["retrieval_val_sha256"] != __import__("hashlib").sha256(
            (DATASET / "retrieval.jsonl").read_bytes()).hexdigest():
            raise RuntimeError("Val changed after dev calibration")
    threshold = calibration["threshold"] if calibration else 0.2
    started_at = datetime.now(timezone.utc)
    result_path, g6_result_path = result_paths(mode, started_at)
    report = {"branch": "e3-h1-synthetic", "dataset_sha256": json.loads((DATASET / "manifest.json").read_text())["hashes"],
              "embedding": embedding.model_version, "gate_closed": False,
              "started_at": started_at.isoformat()}
    pools = None
    with psycopg.connect(owner_dsn, autocommit=True, connect_timeout=10) as admin:
        try:
            with admin.cursor() as cursor:
                cursor.execute("SELECT current_user, current_database(), rolcreatedb FROM pg_roles WHERE rolname=current_user")
                if cursor.fetchone() != ("neondb_owner", "neondb", True):
                    raise RuntimeError("Unexpected Neon owner privileges")
                for database, role, password in identities.values():
                    cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
                    created_roles.append(role)
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
                    created_databases.append(database)
            dsns = {}
            for label, (database, role, password) in identities.items():
                owner_database_dsn = _with_database(owner_dsn, database, "neondb_owner", parsed.password or "")
                with psycopg.connect(owner_database_dsn, connect_timeout=10) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                        cursor.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(role)))
                dsns[label] = _with_database(owner_dsn, database, role, password)
                with psycopg.connect(dsns[label], connect_timeout=10) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute((ROOT / "migrations/knowledge/001_knowledge.sql").read_text())
                        cursor.execute("SELECT current_database(), current_user")
                        if cursor.fetchone() != (database, role):
                            raise RuntimeError("Knowledge identity mismatch")
            pools = KnowledgePools(lambda deployment: dsns[deployment], max_size=4)
            store = PostgresKnowledge(lambda deployment: dsns[deployment], embedding, pools=pools,
                                      known_deployment_labels=frozenset(identities))
            sources = _rows("sources.jsonl")
            generations = {}
            for label in identities:
                deployment_sources = tuple(Source(**source) for source in sources if source["deployment_id"] == label)
                generations[label] = IngestKnowledge(store, embedding)(label, deployment_sources)
                if IngestKnowledge(store, embedding)(label, deployment_sources) != generations[label]:
                    raise RuntimeError("Reingest changed generation")
            report["generations_distinct"] = generations["alpha"] != generations["beta"]
            for label in identities:
                with pools.connection(label):
                    pass
            pools.warm()
            results = []
            for row in _rows("retrieval.jsonl"):
                if row["split"] != "val":
                    continue
                scope = ExecutionScope(row["deployment_id"], "synthetic", row["id"], "actor")
                start = time.perf_counter()
                evidence = store.retrieve(RetrievalQuery(scope, row["query"], "answer"))
                elapsed = time.perf_counter() - start
                results.append((row, evidence, elapsed))
            positives = [(row, evidence) for row, evidence, _ in results if row["answerable"]]
            negatives = [(row, evidence) for row, evidence, _ in results if not row["answerable"]]
            recall = sum(bool({item.source_id for item in evidence if item.score is not None and
                               item.score >= threshold} & set(row["expected_sources"]))
                         for row, evidence in positives) / len(positives)
            abstention = sum(not any(item.score is None or item.score >= threshold for item in evidence)
                             for row, evidence in negatives) / len(negatives)
            cross_leaks = sum(any(item.deployment_id != row["deployment_id"] or
                                  item.source_id == row.get("forbidden_source") for item in evidence)
                              for row, evidence, _ in results)
            latencies = sorted(elapsed for _, _, elapsed in results)
            report.update({"val_queries": len(results), "respondable": len(positives),
                           "unanswerable": len(negatives), "recall_at_5": recall,
                           "abstention": abstention, "threshold_from_dev": threshold,
                           "cross_deployment_leaks": cross_leaks,
                           "p95_seconds": latencies[int(0.95 * (len(latencies) - 1))],
                           "g5_passed": recall >= 0.85 and abstention >= 0.9 and
                           latencies[int(0.95 * (len(latencies) - 1))] <= 1 and cross_leaks == 0})
            if use_api or use_local:
                # Compare both index modes with the same already embedded queries.
                for label in identities:
                    with psycopg.connect(dsns[label], autocommit=True, connect_timeout=10) as connection:
                        connection.execute((ROOT / "migrations/knowledge/002_hnsw_opt_in.sql").read_text())
                hnsw = PostgresKnowledge(lambda deployment: dsns[deployment], embedding,
                                         use_hnsw=True, pools=pools,
                                         known_deployment_labels=frozenset(identities))
                index_differences = 0
                hnsw_recall_hits = 0
                hnsw_respondable = 0
                for row, evidence, _ in results:
                    scope = ExecutionScope(row["deployment_id"], "synthetic", row["id"], "actor")
                    approximate = hnsw.retrieve(RetrievalQuery(scope, row["query"], "answer"))
                    if {item.source_id for item in approximate} != {item.source_id for item in evidence}:
                        index_differences += 1
                    if row["answerable"]:
                        hnsw_respondable += 1
                        hnsw_recall_hits += bool({item.source_id for item in approximate
                                                  if item.score is not None and item.score >= threshold} &
                                                 set(row["expected_sources"]))
                report["hnsw_exact_top5_set_differences"] = index_differences
                report["hnsw_recall_at_5"] = hnsw_recall_hits / hnsw_respondable
            if use_local:
                g6 = run_g6_review(store, result_path=g6_result_path)
                report["g6_assessed"] = True
                report["g6_expected_behavior"] = g6["expected_behavior"]
                report["g6_critical_failures"] = g6["critical_failures"]
            # A failed partial build must not change the active generation.
            bad_sources = (Source("alpha", "alpha-bad-one", "v1", "Prueba parcial uno"),
                           Source("alpha", "alpha-bad-two", "v1", "Prueba parcial dos"))
            good_vector = embedding.embed((bad_sources[0].content,))[0]
            try:
                store.publish("alpha", bad_sources, (good_vector, good_vector[:-1]),
                              embedding.model_version)
            except ValueError:
                pass
            else:
                raise RuntimeError("Invalid vector did not fail")
            with pools.connection("alpha") as connection:
                active_after_failure = connection.execute(
                    "SELECT generation_id FROM knowledge_generations WHERE status='ACTIVE'").fetchone()[0]
                partial_rows = connection.execute(
                    "SELECT count(*) FROM knowledge_sources WHERE source_id LIKE 'alpha-bad-%'").fetchone()[0]
            report["partial_generation_invisible"] = (
                active_after_failure == generations["alpha"] and partial_rows == 0)
            # Publish a new generation, then atomically restore the old one.
            updated_sources = tuple(Source(**({**source, "version": "v2",
                                               "content": source["content"] + " Versión nueva."}
                                             if source["source_id"] == "alpha-guide-01" else source))
                                    for source in sources if source["deployment_id"] == "alpha")
            new_generation = IngestKnowledge(store, embedding)("alpha", updated_sources)
            store.activate_generation("alpha", generations["alpha"])
            with pools.connection("alpha") as connection:
                active_after_rollback = connection.execute(
                    "SELECT generation_id FROM knowledge_generations WHERE status='ACTIVE'").fetchone()[0]
            report["reindex_rollback_restored"] = (
                new_generation != generations["alpha"] and
                active_after_rollback == generations["alpha"])
            # Revocation must affect the next query without republishing.
            store.revoke("alpha", "alpha-guide-01")
            probe = store.retrieve(RetrievalQuery(ExecutionScope("alpha", "synthetic", "revoke", "actor"),
                                                  "guía 1 de alpha", "answer"))
            report["revocation_excluded"] = all(item.source_id != "alpha-guide-01" for item in probe)
            report.setdefault("g6_assessed", False)
            if budget:
                report["embedding_budget"] = budget.snapshot()
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            result_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(json.dumps({key: report[key] for key in ("val_queries", "recall_at_5", "abstention",
                                                           "cross_deployment_leaks", "p95_seconds",
                                                           "revocation_excluded", "g5_passed", "gate_closed")}))
            return 0
        finally:
            if pools is not None:
                pools.close()
            if isinstance(api_embedding, OpenAIEmbedding):
                api_embedding.close()
            with admin.cursor() as cursor:
                for database in reversed(created_databases):
                    cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
                for role in reversed(created_roles):
                    cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


if __name__ == "__main__":
    raise SystemExit(main())
