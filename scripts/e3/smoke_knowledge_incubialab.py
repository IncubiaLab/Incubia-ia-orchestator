"""End-to-end smoke of RAG IncubiaLab Knowledge on the isolated Neon branch.

Publishes three synthetic sources with the ingestor role, retrieves them through
``compose_incubialab_retrieval`` (runtime role), checks deployment isolation and
that the runtime role cannot write, then deletes the synthetic rows. Uses the
offline ``HashEmbedding``: this proves wiring, grants and SQL, not retrieval
quality. Reads deploy/knowledge-neon.env overlaid by .env; prints no secrets.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from incubia_orchestrator.bootstrap.knowledge_incubialab import (  # noqa: E402
    DEPLOYMENT_ENV_VAR, compose_incubialab_retrieval)
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope  # noqa: E402
from incubia_orchestrator.modules.knowledge.adapters.embedding import HashEmbedding  # noqa: E402
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge  # noqa: E402
from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import (  # noqa: E402
    knowledge_ingest_resolver)
from incubia_orchestrator.modules.knowledge.domain import RetrievalQuery, Source  # noqa: E402
from scripts.e3.migrate_knowledge import EXPECTED_BRANCH, load_env_file  # noqa: E402
from scripts.e3.neon_branch_guard import require_isolated_branch  # noqa: E402

PREFIX = "synthetic-smoke:"
DOCS = (
    ("incubadora", "IncubiaLab acompaña a startups en etapa temprana con mentorías semanales."),
    ("convocatoria", "La convocatoria de primavera abre en marzo y cierra el quince de abril."),
    ("espacio", "El espacio de coworking está disponible de lunes a viernes de ocho a veinte."),
)


def _check(label: str, ok: bool) -> bool:
    print(f"{'OK   ' if ok else 'FALLA'} {label}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, action="append",
                        help="repeatable; later files win (default: deploy/knowledge-neon.env then .env)")
    parser.add_argument("--deployment-id", default=None)
    args = parser.parse_args(argv)
    env: dict[str, str] = {}
    for path in args.env_file or (ROOT / "deploy/knowledge-neon.env", ROOT / ".env"):
        if path.is_file():
            env.update(load_env_file(path))
    deployment = args.deployment_id or env.get(DEPLOYMENT_ENV_VAR) or ""
    env[DEPLOYMENT_ENV_VAR] = deployment
    require_isolated_branch(env.get("INCUBIA_KNOWLEDGE_NEON_BRANCH"), expected=EXPECTED_BRANCH)

    embedding = HashEmbedding()
    ingest = PostgresKnowledge(knowledge_ingest_resolver(env, deployment_id=deployment), embedding)
    runtime = compose_incubialab_retrieval(env, embedding)
    run = uuid4().hex[:8]
    sources = [Source(deployment, f"{PREFIX}{run}:{key}", "v1", text, f"https://example.invalid/{key}")
               for key, text in DOCS]
    scope = ExecutionScope(deployment, "synthetic-tenant", f"smoke-{run}", "synthetic-actor")
    results, generation = [], None
    try:
        generation = ingest.publish(deployment, sources, embedding.embed([s.content for s in sources]),
                                    embedding.model_version)
        results.append(_check("ingestor publica generación ACTIVE", bool(generation)))
        hits = runtime.retrieve(RetrievalQuery(scope, "¿Cuándo cierra la convocatoria de primavera?",
                                               "knowledge.search", top_k=3))
        results.append(_check("runtime recupera 3 evidencias", len(hits) == 3))
        results.append(_check("top-1 es la fuente correcta",
                              bool(hits) and hits[0].source_id.endswith(":convocatoria")))
        results.append(_check("evidencias de la generación activa",
                              all(hit.generation_id == generation for hit in hits)))
        foreign = ExecutionScope("otro-deployment", "t", f"smoke-{run}", "a")
        try:
            runtime.retrieve(RetrievalQuery(foreign, "convocatoria", "knowledge.search"))
            results.append(_check("deployment ajeno denegado", False))
        except ValueError:
            results.append(_check("deployment ajeno denegado", True))
        try:
            runtime.publish(deployment, sources[:1], embedding.embed([sources[0].content]),
                            embedding.model_version + "-rw")
            results.append(_check("runtime no puede escribir", False))
        except Exception as exc:
            results.append(_check("runtime no puede escribir", type(exc).__name__ == "InsufficientPrivilege"))
    except Exception as exc:
        print(f"FALLA smoke interrumpido ({type(exc).__name__})")
        results.append(False)
    finally:
        _cleanup(ingest, deployment, generation, run)
        runtime._pools.close()
    return 0 if results and all(results) else 1


def _cleanup(ingest: PostgresKnowledge, deployment: str, generation: str | None, run: str) -> None:
    try:
        with ingest._connect(deployment) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM knowledge_chunks WHERE source_id LIKE %s", (f"{PREFIX}{run}:%",))
            if generation:
                cursor.execute("DELETE FROM knowledge_generations WHERE generation_id=%s", (generation,))
            cursor.execute("DELETE FROM knowledge_sources WHERE source_id LIKE %s", (f"{PREFIX}{run}:%",))
            cursor.execute("SELECT (SELECT count(*) FROM knowledge_generations), "
                           "(SELECT count(*) FROM knowledge_sources), (SELECT count(*) FROM knowledge_chunks)")
            print(f"cleanup: filas restantes generations/sources/chunks = {cursor.fetchone()}")
    except Exception as exc:
        print(f"FALLA cleanup ({type(exc).__name__}); revisar filas {PREFIX}{run}:*")


if __name__ == "__main__":
    raise SystemExit(main())
