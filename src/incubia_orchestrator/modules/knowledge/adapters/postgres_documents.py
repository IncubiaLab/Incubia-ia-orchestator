"""PostgreSQL + pgvector document store for workspace-scoped Orbit Knowledge."""
from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import json
import re
from uuid import uuid4

from incubia_orchestrator.modules.knowledge.adapters.pool import KnowledgePools
from incubia_orchestrator.modules.knowledge.adapters.postgres import _vector
from incubia_orchestrator.modules.knowledge.domain import AccessTier, KnowledgeStoreUnavailable, WorkspaceKnowledgeHit


_KW_STOPWORDS = frozenset({
    "que", "como", "cual", "cuales", "para", "por", "con", "sin", "los", "las",
    "del", "una", "uno", "unos", "unas", "sobre", "entre", "esto", "esta", "este",
    "esos", "esas", "son", "fue", "han", "hay", "resume", "dime", "dame", "the",
    "and", "for", "with", "what", "how",
})


def _or_tsquery_text(query_text: str) -> str:
    tokens = [
        tok for tok in re.findall(r"[A-Za-z0-9]{3,}", query_text.lower())
        if tok not in _KW_STOPWORDS
    ]
    # Deduplicate preserving order, bounded to avoid oversized tsquery.
    unique = list(dict.fromkeys(tokens))[:12]
    return " | ".join(unique)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _workspace_prefix(workspace_id: str) -> str:
    return f"orbit:{_escape_like(workspace_id)}:%"


def _document_prefix(workspace_id: str, document_id: str) -> str:
    return f"orbit:{_escape_like(workspace_id)}:{_escape_like(document_id)}:%"


def _chunk_source_id(workspace_id: str, document_id: str, index: int) -> str:
    return f"orbit:{workspace_id}:{document_id}:{index}"


def _parse_public_ref(raw_ref: str | None, fallback_source_id: str) -> tuple[str, str, str]:
    if not raw_ref:
        return fallback_source_id, fallback_source_id, ""
    try:
        parsed = json.loads(raw_ref)
        if isinstance(parsed, dict):
            return (
                str(parsed.get("sourceId") or fallback_source_id),
                str(parsed.get("title") or fallback_source_id),
                str(parsed.get("documentId") or ""),
            )
    except Exception:
        pass
    return fallback_source_id, raw_ref, ""


class PostgresOrbitKnowledgeStore:
    """Stores and retrieves Orbit workspace documents across separate ingestor and runtime pools."""

    def __init__(self, *, ingest_pools: KnowledgePools, runtime_pools: KnowledgePools):
        self._ingest_pools = ingest_pools
        self._runtime_pools = runtime_pools

    def ready(self, deployment_id: str) -> bool:
        try:
            with self._runtime_pools.connection(deployment_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return cursor.fetchone() == (1,)
        except Exception:
            return False

    def close(self) -> None:
        self._ingest_pools.close()
        self._runtime_pools.close()

    def is_document_active(
        self,
        deployment_id: str,
        workspace_id: str,
        document_id: str,
        version: str,
        model_version: str,
    ) -> str | None:
        doc_pattern = _document_prefix(workspace_id, document_id)
        try:
            with self._runtime_pools.connection(deployment_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT g.generation_id
                        FROM knowledge_chunks c
                        JOIN knowledge_generations g ON g.generation_id = c.generation_id
                        JOIN knowledge_sources s ON s.source_id = c.source_id
                        WHERE g.status = 'ACTIVE'
                          AND g.model_version = %s
                          AND c.source_id LIKE %s ESCAPE '\\'
                          AND c.source_version = %s
                          AND s.revoked_at IS NULL
                        LIMIT 1
                        """,
                        (model_version, doc_pattern, version),
                    )
                    row = cursor.fetchone()
                    return str(row[0]) if row else None
        except Exception as exc:
            raise KnowledgeStoreUnavailable("Knowledge readiness check failed") from exc

    def upsert_document(
        self,
        deployment_id: str,
        workspace_id: str,
        document_id: str,
        source_id: str,
        version: str,
        title: str,
        chunks: Sequence[str],
        embeddings: Sequence[tuple[float, ...]],
        model_version: str,
        *,
        access_tier: AccessTier = AccessTier.ADMIN_ONLY,
    ) -> tuple[str, str]:
        if not chunks or len(chunks) != len(embeddings):
            raise ValueError("Document chunks and embeddings must be non-empty and aligned")
        tier_value = AccessTier(access_tier).value

        doc_pattern = _document_prefix(workspace_id, document_id)
        public_ref = json.dumps(
            {
                "sourceId": source_id,
                "documentId": document_id,
                "workspaceId": workspace_id,
                "title": title[:200],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        chunk_rows = [
            (
                _chunk_source_id(workspace_id, document_id, idx),
                version,
                chunk_text,
                sha256(chunk_text.encode("utf-8")).hexdigest(),
                _vector(vec),
            )
            for idx, (chunk_text, vec) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        new_source_ids = [row[0] for row in chunk_rows]

        try:
            with self._ingest_pools.connection(deployment_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('knowledge_publish'))")
                    cursor.execute(
                        "SELECT generation_id, model_version FROM knowledge_generations WHERE status = 'ACTIVE' LIMIT 1"
                    )
                    active_row = cursor.fetchone()
                    active_gen_id = str(active_row[0]) if active_row else None
                    active_model = str(active_row[1]) if active_row else None

                    if active_gen_id and active_model == model_version:
                        cursor.execute(
                            """
                            SELECT 1
                            FROM knowledge_chunks c
                            JOIN knowledge_sources s ON s.source_id = c.source_id
                            WHERE c.generation_id = %s
                              AND c.source_id LIKE %s ESCAPE '\\'
                              AND c.source_version = %s
                              AND s.revoked_at IS NULL
                            LIMIT 1
                            """,
                            (active_gen_id, doc_pattern, version),
                        )
                        if cursor.fetchone() is not None:
                            return "already_indexed", active_gen_id

                    # Revoke stale extra chunk indices if an updated version has fewer chunks.
                    cursor.execute(
                        """
                        UPDATE knowledge_sources
                        SET revoked_at = now()
                        WHERE source_id LIKE %s ESCAPE '\\'
                          AND NOT (source_id = ANY(%s))
                        """,
                        (doc_pattern, new_source_ids),
                    )

                    for chunk_src_id, chunk_ver, _text, content_hash, _vec in chunk_rows:
                        cursor.execute(
                            """
                            INSERT INTO knowledge_sources (source_id, version, content_hash, public_ref, revoked_at, access_tier)
                            VALUES (%s, %s, %s, %s, NULL, %s)
                            ON CONFLICT (source_id) DO UPDATE SET
                                version = EXCLUDED.version,
                                content_hash = EXCLUDED.content_hash,
                                public_ref = EXCLUDED.public_ref,
                                revoked_at = NULL,
                                access_tier = EXCLUDED.access_tier
                            """,
                            (chunk_src_id, chunk_ver, content_hash, public_ref, tier_value),
                        )

                    surviving_meta: list[tuple[str, str, str]] = []
                    can_carry_over = bool(active_gen_id and active_model == model_version)
                    if can_carry_over:
                        cursor.execute(
                            """
                            SELECT c.source_id, c.source_version, s.content_hash
                            FROM knowledge_chunks c
                            JOIN knowledge_sources s ON s.source_id = c.source_id
                            WHERE c.generation_id = %s
                              AND s.revoked_at IS NULL
                              AND c.source_id NOT LIKE %s ESCAPE '\\'
                            ORDER BY c.chunk_id
                            """,
                            (active_gen_id, doc_pattern),
                        )
                        surviving_meta = [(str(r[0]), str(r[1]), str(r[2])) for r in cursor.fetchall()]

                    corpus_entries = sorted(
                        surviving_meta + [(r[0], r[1], r[3]) for r in chunk_rows]
                    )
                    corpus_digest = sha256(
                        json.dumps(
                            ("orbit-chunks-v1", model_version, corpus_entries),
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    new_generation_id = f"{corpus_digest[:24]}{uuid4().hex[:8]}"

                    cursor.execute(
                        """
                        INSERT INTO knowledge_generations (generation_id, status, model_version, dimension, corpus_hash)
                        VALUES (%s, 'BUILDING', %s, 384, %s)
                        """,
                        (new_generation_id, model_version, corpus_digest),
                    )

                    if can_carry_over and surviving_meta:
                        cursor.execute(
                            """
                            INSERT INTO knowledge_chunks (generation_id, source_id, source_version, chunk_id, content, embedding)
                            SELECT %s, c.source_id, c.source_version, c.chunk_id, c.content, c.embedding
                            FROM knowledge_chunks c
                            JOIN knowledge_sources s ON s.source_id = c.source_id
                            WHERE c.generation_id = %s
                              AND s.revoked_at IS NULL
                              AND c.source_id NOT LIKE %s ESCAPE '\\'
                            """,
                            (new_generation_id, active_gen_id, doc_pattern),
                        )

                    for chunk_src_id, chunk_ver, chunk_text, _content_hash, vec_sql in chunk_rows:
                        cursor.execute(
                            """
                            INSERT INTO knowledge_chunks (generation_id, source_id, source_version, chunk_id, content, embedding)
                            VALUES (%s, %s, %s, %s, %s, %s::vector)
                            """,
                            (new_generation_id, chunk_src_id, chunk_ver, chunk_src_id, chunk_text, vec_sql),
                        )

                    cursor.execute(
                        "UPDATE knowledge_generations SET status = 'VALIDATING' WHERE generation_id = %s",
                        (new_generation_id,),
                    )
                    cursor.execute(
                        "SELECT count(*) FROM knowledge_chunks WHERE generation_id = %s",
                        (new_generation_id,),
                    )
                    expected_count = len(surviving_meta) + len(chunk_rows)
                    if int(cursor.fetchone()[0]) != expected_count:
                        raise KnowledgeStoreUnavailable("Incomplete Knowledge generation")

                    cursor.execute(
                        "UPDATE knowledge_generations SET status = 'RETIRED' WHERE status = 'ACTIVE'"
                    )
                    cursor.execute(
                        "UPDATE knowledge_generations SET status = 'ACTIVE' WHERE generation_id = %s",
                        (new_generation_id,),
                    )
                    return "indexed", new_generation_id
        except KnowledgeStoreUnavailable:
            raise
        except Exception as exc:
            raise KnowledgeStoreUnavailable("Failed to upsert Knowledge document") from exc

    def revoke_document(
        self,
        deployment_id: str,
        workspace_id: str,
        document_id: str,
        source_id: str,
    ) -> tuple[str, str | None]:
        doc_pattern = _document_prefix(workspace_id, document_id)
        try:
            with self._ingest_pools.connection(deployment_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('knowledge_publish'))")
                    cursor.execute(
                        "SELECT generation_id, model_version FROM knowledge_generations WHERE status = 'ACTIVE' LIMIT 1"
                    )
                    active_row = cursor.fetchone()
                    active_gen_id = str(active_row[0]) if active_row else None
                    active_model = str(active_row[1]) if active_row else None

                    cursor.execute(
                        """
                        SELECT count(*) FILTER (WHERE revoked_at IS NULL)
                        FROM knowledge_sources
                        WHERE source_id LIKE %s ESCAPE '\\'
                        """,
                        (doc_pattern,),
                    )
                    unrevoked_count = int(cursor.fetchone()[0])

                    active_target_count = 0
                    if active_gen_id:
                        cursor.execute(
                            """
                            SELECT count(*)
                            FROM knowledge_chunks
                            WHERE generation_id = %s AND source_id LIKE %s ESCAPE '\\'
                            """,
                            (active_gen_id, doc_pattern),
                        )
                        active_target_count = int(cursor.fetchone()[0])

                    if unrevoked_count == 0 and active_target_count == 0:
                        return "already_revoked", active_gen_id

                    cursor.execute(
                        """
                        UPDATE knowledge_sources
                        SET revoked_at = now()
                        WHERE source_id LIKE %s ESCAPE '\\' AND revoked_at IS NULL
                        """,
                        (doc_pattern,),
                    )

                    if not active_gen_id or active_target_count == 0:
                        return "revoked", active_gen_id

                    cursor.execute(
                        """
                        SELECT c.source_id, c.source_version, s.content_hash
                        FROM knowledge_chunks c
                        JOIN knowledge_sources s ON s.source_id = c.source_id
                        WHERE c.generation_id = %s
                          AND s.revoked_at IS NULL
                          AND c.source_id NOT LIKE %s ESCAPE '\\'
                        ORDER BY c.chunk_id
                        """,
                        (active_gen_id, doc_pattern),
                    )
                    surviving_meta = [(str(r[0]), str(r[1]), str(r[2])) for r in cursor.fetchall()]

                    if not surviving_meta:
                        cursor.execute(
                            "UPDATE knowledge_generations SET status = 'RETIRED' WHERE generation_id = %s",
                            (active_gen_id,),
                        )
                        return "revoked", None

                    corpus_digest = sha256(
                        json.dumps(
                            ("orbit-chunks-v1", active_model, sorted(surviving_meta)),
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    new_generation_id = f"{corpus_digest[:24]}{uuid4().hex[:8]}"

                    cursor.execute(
                        """
                        INSERT INTO knowledge_generations (generation_id, status, model_version, dimension, corpus_hash)
                        VALUES (%s, 'BUILDING', %s, 384, %s)
                        """,
                        (new_generation_id, active_model, corpus_digest),
                    )
                    cursor.execute(
                        """
                        INSERT INTO knowledge_chunks (generation_id, source_id, source_version, chunk_id, content, embedding)
                        SELECT %s, c.source_id, c.source_version, c.chunk_id, c.content, c.embedding
                        FROM knowledge_chunks c
                        JOIN knowledge_sources s ON s.source_id = c.source_id
                        WHERE c.generation_id = %s
                          AND s.revoked_at IS NULL
                          AND c.source_id NOT LIKE %s ESCAPE '\\'
                        """,
                        (new_generation_id, active_gen_id, doc_pattern),
                    )
                    cursor.execute(
                        "UPDATE knowledge_generations SET status = 'VALIDATING' WHERE generation_id = %s",
                        (new_generation_id,),
                    )
                    cursor.execute(
                        "UPDATE knowledge_generations SET status = 'RETIRED' WHERE status = 'ACTIVE'"
                    )
                    cursor.execute(
                        "UPDATE knowledge_generations SET status = 'ACTIVE' WHERE generation_id = %s",
                        (new_generation_id,),
                    )
                    return "revoked", new_generation_id
        except KnowledgeStoreUnavailable:
            raise
        except Exception as exc:
            raise KnowledgeStoreUnavailable("Failed to revoke Knowledge document") from exc

    def retrieve_workspace(
        self,
        deployment_id: str,
        workspace_id: str,
        query_vector: Sequence[float],
        model_version: str,
        *,
        top_k: int = 5,
        query_text: str = "",
        allowed_tiers: frozenset[str] | None = None,
    ) -> tuple[WorkspaceKnowledgeHit, ...]:
        # Fail-closed: if caller omits allowed_tiers, restrict to workspace_general only.
        if allowed_tiers is None:
            tier_filter = [AccessTier.WORKSPACE_GENERAL.value]
        else:
            tier_filter = sorted(
                t for t in allowed_tiers if t in {AccessTier.WORKSPACE_GENERAL.value, AccessTier.ADMIN_ONLY.value}
            )
        if not tier_filter:
            return ()

        encoded = _vector(query_vector)
        ws_pattern = _workspace_prefix(workspace_id)
        limit = max(1, min(top_k, 10))
        or_query = _or_tsquery_text(query_text)
        try:
            with self._runtime_pools.connection(deployment_id) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        WITH active_chunks AS MATERIALIZED (
                            SELECT c.generation_id, c.source_id, c.chunk_id, c.content, c.embedding, s.public_ref, s.access_tier
                            FROM knowledge_chunks c
                            JOIN knowledge_generations g ON g.generation_id = c.generation_id
                            JOIN knowledge_sources s ON s.source_id = c.source_id
                            WHERE g.status = 'ACTIVE'
                              AND g.model_version = %s
                              AND c.source_id LIKE %s ESCAPE '\\'
                              AND s.revoked_at IS NULL
                              AND s.access_tier = ANY(%s)
                        ),
                        ranked AS (
                            SELECT generation_id, source_id, chunk_id, content, public_ref, access_tier,
                                   1 - (embedding <=> %s::vector) AS vec_score,
                                   CASE
                                       WHEN nullif(%s, '') IS NOT NULL
                                            AND to_tsvector('simple', coalesce(public_ref, '') || ' ' || content)
                                                @@ to_tsquery('simple', nullif(%s, ''))
                                       THEN ts_rank_cd(
                                           to_tsvector('simple', coalesce(public_ref, '') || ' ' || content),
                                           to_tsquery('simple', nullif(%s, ''))
                                       )
                                       ELSE 0.0
                                   END AS kw_score,
                                   row_number() OVER (
                                       PARTITION BY split_part(source_id, ':', 3)
                                       ORDER BY embedding <=> %s::vector, chunk_id
                                   ) AS doc_rank
                            FROM active_chunks
                        )
                        SELECT generation_id, source_id, chunk_id, content, public_ref, access_tier,
                               LEAST(1.0, vec_score + LEAST(0.35, kw_score * 0.25)) AS score
                        FROM ranked
                        WHERE doc_rank <= 2
                        ORDER BY (vec_score + LEAST(0.35, kw_score * 0.25)) DESC, chunk_id
                        LIMIT %s
                        """,
                        (model_version, ws_pattern, tier_filter, encoded, or_query, or_query, or_query, encoded, limit),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            raise KnowledgeStoreUnavailable("Workspace Knowledge retrieval failed") from exc

        hits: list[WorkspaceKnowledgeHit] = []
        for gen_id, chunk_src_id, chunk_id, content, raw_ref, raw_tier, raw_score in rows:
            source_id, title, doc_id = _parse_public_ref(raw_ref, str(chunk_src_id))
            score = max(0.0, min(1.0, float(raw_score))) if raw_score is not None else 0.0
            try:
                hit_tier = AccessTier(str(raw_tier))
            except ValueError:
                hit_tier = AccessTier.ADMIN_ONLY
            hits.append(
                WorkspaceKnowledgeHit(
                    deployment_id=deployment_id,
                    workspace_id=workspace_id,
                    document_id=doc_id,
                    source_id=source_id,
                    chunk_id=str(chunk_id),
                    generation_id=str(gen_id),
                    title=title,
                    text=str(content),
                    score=score,
                    access_tier=hit_tier,
                )
            )
        return tuple(hits)

