"""pgvector store selected by a trusted deployment-to-DSN resolver."""
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re

from incubia_orchestrator.modules.knowledge.domain import EmbeddingUnavailable, EvidenceItem, RetrievalQuery, Source
from incubia_orchestrator.modules.knowledge.ports import EmbeddingPort


def _vector(values: Sequence[float]) -> str:
    if len(values) != 384 or any(not math.isfinite(value) for value in values):
        raise ValueError("Expected 384 finite embedding values")
    return "[" + ",".join(format(value, ".9g") for value in values) + "]"


class PostgresKnowledge:
    """One connection pool/DSN per deployment, supplied by trusted Control Plane code."""

    def __init__(self, resolve_dsn: Callable[[str], str], embedding: EmbeddingPort,
                 *, use_hnsw: bool = False, pools=None,
                 known_deployment_labels: frozenset[str] = frozenset()):
        if embedding.dimension != 384:
            raise ValueError("Knowledge schema requires dimension 384")
        self._resolve_dsn, self._embedding = resolve_dsn, embedding
        self._use_hnsw = use_hnsw
        self._pools = pools
        self._known_deployment_labels = frozenset(label.casefold() for label in known_deployment_labels)
        self.embedding_ready = True

    def _connect(self, deployment_id: str):
        if not deployment_id:
            raise ValueError("Trusted deployment ID is required")
        if self._pools is not None:
            return self._pools.connection(deployment_id)
        import psycopg
        dsn = self._resolve_dsn(deployment_id)
        if not dsn:
            raise ValueError("Deployment has no configured Knowledge database")
        return psycopg.connect(dsn, connect_timeout=3)

    def publish(self, deployment_id: str, sources: Sequence[Source],
                embeddings: Sequence[tuple[float, ...]], model_version: str) -> str:
        if not sources or len(sources) != len(embeddings) or not model_version:
            raise ValueError("Complete corpus, embeddings and model are required")
        if any(source.deployment_id != deployment_id or source.revoked for source in sources):
            raise ValueError("Source is outside deployment or revoked")
        corpus = sorted((source.source_id, source.version, sha256(source.content.encode()).hexdigest(),
                         source.public_ref)
                        for source in sources)
        digest = sha256(json.dumps(("single-chunk-v1", model_version, corpus),
                                   separators=(",", ":")).encode()).hexdigest()
        generation_id = digest[:32]
        with self._connect(deployment_id) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('knowledge_publish'))")
                cursor.execute("SELECT status FROM knowledge_generations WHERE generation_id=%s", (generation_id,))
                existing = cursor.fetchone()
                if existing:
                    if existing[0] == "ACTIVE":
                        return generation_id
                    raise ValueError("Generation ID already exists in non-active state")
                cursor.execute("INSERT INTO knowledge_generations "
                               "(generation_id,status,model_version,dimension,corpus_hash) "
                               "VALUES (%s,'BUILDING',%s,384,%s)", (generation_id, model_version, digest))
                for index, (source, vector) in enumerate(zip(sources, embeddings, strict=True)):
                    content_hash = sha256(source.content.encode()).hexdigest()
                    cursor.execute("SELECT revoked_at FROM knowledge_sources WHERE source_id=%s", (source.source_id,))
                    previous = cursor.fetchone()
                    if previous and previous[0] is not None:
                        raise ValueError("Revoked source cannot be reactivated by ingest")
                    cursor.execute("INSERT INTO knowledge_sources(source_id,version,content_hash,public_ref) "
                                   "VALUES (%s,%s,%s,%s) ON CONFLICT(source_id) DO UPDATE SET "
                                   "version=EXCLUDED.version,content_hash=EXCLUDED.content_hash,"
                                   "public_ref=EXCLUDED.public_ref",
                                   (source.source_id, source.version, content_hash, source.public_ref))
                    cursor.execute("INSERT INTO knowledge_chunks "
                                   "(generation_id,source_id,source_version,chunk_id,content,embedding) "
                                   "VALUES (%s,%s,%s,%s,%s,%s::vector)",
                                   (generation_id, source.source_id, source.version,
                                    f"{source.source_id}:{index}", source.content, _vector(vector)))
                cursor.execute("UPDATE knowledge_generations SET status='VALIDATING' WHERE generation_id=%s",
                               (generation_id,))
                cursor.execute("SELECT count(*) FROM knowledge_chunks WHERE generation_id=%s", (generation_id,))
                if cursor.fetchone()[0] != len(sources):
                    raise RuntimeError("Incomplete Knowledge generation")
                cursor.execute("UPDATE knowledge_generations SET status='RETIRED' WHERE status='ACTIVE'")
                cursor.execute("UPDATE knowledge_generations SET status='ACTIVE' WHERE generation_id=%s",
                               (generation_id,))
                cursor.execute("SELECT source_id,source_version,content FROM knowledge_chunks "
                               "WHERE generation_id=%s", (generation_id,))
                for source_id, version, content in cursor.fetchall():
                    cursor.execute("UPDATE knowledge_sources SET version=%s,content_hash=%s "
                                   "WHERE source_id=%s",
                                   (version, sha256(content.encode()).hexdigest(), source_id))
        return generation_id

    def revoke(self, deployment_id: str, source_id: str) -> None:
        if not source_id:
            raise ValueError("Source ID required")
        with self._connect(deployment_id) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE knowledge_sources SET revoked_at=now() WHERE source_id=%s", (source_id,))

    def activate_generation(self, deployment_id: str, generation_id: str) -> None:
        """Atomically roll back to a complete retired generation of the same model."""
        if not generation_id:
            raise ValueError("Generation ID required")
        with self._connect(deployment_id) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('knowledge_publish'))")
                cursor.execute("SELECT status,model_version,dimension FROM knowledge_generations "
                               "WHERE generation_id=%s FOR UPDATE", (generation_id,))
                row = cursor.fetchone()
                if row is None or row[0] not in {"RETIRED", "ACTIVE"} or row[1] != self._embedding.model_version or row[2] != 384:
                    raise ValueError("Generation is unavailable or incompatible")
                if row[0] == "ACTIVE":
                    return
                cursor.execute("SELECT count(*) FROM knowledge_chunks WHERE generation_id=%s", (generation_id,))
                if cursor.fetchone()[0] == 0:
                    raise ValueError("Empty generation cannot be activated")
                cursor.execute("UPDATE knowledge_generations SET status='RETIRED' WHERE status='ACTIVE'")
                cursor.execute("UPDATE knowledge_generations SET status='ACTIVE' WHERE generation_id=%s",
                               (generation_id,))

    def retrieve(self, query: RetrievalQuery) -> tuple[EvidenceItem, ...]:
        if query.deadline is not None and datetime.now(timezone.utc) >= query.deadline:
            return ()
        # This is an early abstention hint for explicit foreign references.
        # Database selection remains the security boundary even if wording evades it.
        words = set(re.findall(r"\w+", query.text.casefold()))
        if any(label != query.scope.deployment_id.casefold() and label in words
               for label in self._known_deployment_labels):
            return ()
        try:
            vector = self._embedding.embed((query.text,))
        except Exception:
            # Provider exceptions may include request bodies or credentials.
            vector = None
        if vector is None:
            self.embedding_ready = False
            raise EmbeddingUnavailable("Embedding request failed")
        self.embedding_ready = True
        if len(vector) != 1:
            raise ValueError("Embedding adapter returned wrong batch size")
        encoded = _vector(vector[0])
        with self._connect(query.scope.deployment_id) as connection:
            with connection.cursor() as cursor:
                if self._use_hnsw:
                    cursor.execute("SELECT to_regclass('knowledge_chunks_hnsw_idx')")
                    if cursor.fetchone()[0] is None:
                        raise RuntimeError("HNSW flag requires the evaluated index")
                    cursor.execute("SET LOCAL enable_seqscan = off")
                    cursor.execute("SELECT g.generation_id,c.source_id,c.source_version,c.chunk_id,c.content,"
                                   "s.public_ref,1-(c.embedding <=> %s::vector) AS score "
                                   "FROM knowledge_chunks c JOIN knowledge_generations g "
                                   "ON g.generation_id=c.generation_id JOIN knowledge_sources s "
                                   "ON s.source_id=c.source_id WHERE g.status='ACTIVE' "
                                   "AND g.model_version=%s AND s.revoked_at IS NULL "
                                   "ORDER BY c.embedding <=> %s::vector, c.chunk_id LIMIT %s",
                                   (encoded, self._embedding.model_version, encoded, query.top_k))
                else:
                    # Materialization makes this an exact scan even if an HNSW
                    # index exists, without extra SET LOCAL round trips.
                    cursor.execute("WITH active_chunks AS MATERIALIZED ("
                                   "SELECT c.generation_id,c.source_id,c.source_version,c.chunk_id,"
                                   "c.content,c.embedding FROM knowledge_chunks c "
                                   "JOIN knowledge_generations g ON g.generation_id=c.generation_id "
                                   "WHERE g.status='ACTIVE' AND g.model_version=%s) "
                                   "SELECT c.generation_id,c.source_id,c.source_version,c.chunk_id,"
                                   "c.content,s.public_ref,1-(c.embedding <=> %s::vector) AS score "
                                   "FROM active_chunks c JOIN knowledge_sources s ON s.source_id=c.source_id "
                                   "WHERE s.revoked_at IS NULL "
                                   "ORDER BY c.embedding <=> %s::vector, c.chunk_id LIMIT %s",
                                   (self._embedding.model_version, encoded, encoded, query.top_k))
                rows = cursor.fetchall()
        return tuple(EvidenceItem(query.scope.deployment_id, row[1], row[2], row[3], row[0],
                                  row[4], max(0.0, min(1.0, float(row[6]))), row[5]) for row in rows)
