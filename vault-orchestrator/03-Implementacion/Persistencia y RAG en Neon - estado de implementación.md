---
tipo: implementacion
estado: gates-e3-1-e3-2-e3-4-cerrados-integracion-vps-pendiente
fecha: 2026-11-11
---

# Persistencia y RAG en Neon — estado de implementación

## Implementado y verificado

- **Ledger PostgreSQL y RLS (`E3-1`, `E3-2` cerrados):** migraciones `001`–`007`, `PostgresLedger`, `PooledConnections`, `h1_backup.py` (export/import idempotente con hash SHA-256 y `restore_audit`) y suites de concurrencia/fencing (`tests/integration/neon/`).
- **Knowledge Base y Retrieval (`E3-4` cerrado):** migraciones `migrations/knowledge/001..002`, `KnowledgePools`, resolver fail-closed `runtime_dsn.py`, `compose_incubialab_retrieval` en `bootstrap/knowledge_incubialab.py`, transporte Google Drive con service account (`adapters/drive_http.py`), caso de uso `drive_ingest.py` y adaptador `openai_embedding.py` con presupuesto durable.
- **Evidencia en `evals/results/`:**
  - `e3-1-campaign-2026-10-13-final.json` (offline 27/27, Compose y Neon 8/8).
  - `e3-2-campaign-2026-10-15-local.json` (local 17/17 y Neon 9/9).
  - `e3-4-neon-local-20261024T034222Z.json` y `e3-4-g6-neon-local-20261024T034222Z.json` (recall/abstención `1,00`, `p95 = 0,592 s`, 24 casos G6 aprobados).

## Pendiente

- [ ] Conectar `compose_incubialab_retrieval` + `openai_embedding_from_env` a la entrada productiva del orchestrator (ver `TODOS.md` §5 y `PLAN-VPS.md`).
- [ ] Completar credenciales de service account Drive y validación de ACL de carpeta antes de ejecutar `scripts/e3/ingest_drive_knowledge.py --apply --acl-reviewed` (`TODOS.md` §2–4).
- [ ] Extender el procedimiento de backup/restore para cubrir `audit_events` y la base Knowledge en la campaña `E3-5`.

[[01-Investigacion/Persistencia-y-RAG-Neon/Investigacion - persistencia y RAG en Neon]] · [[Persistencia y RAG en Neon - beneficios]] · [[Persistencia y RAG en Neon - contras y riesgos]] · [[Persistencia y RAG en Neon - decisión]]
