---
tipo: investigacion
tema: Persistencia y RAG en Neon
estado: revisado
fecha: 2026-11-11
---

# Investigación — persistencia y RAG en Neon

## Pregunta y alcance

¿Cómo garantizar aislamiento multi-tenant, durabilidad conversacional con fencing transaccional y recuperación semántica (RAG con `pgvector`) sobre Neon PostgreSQL sin fugas entre deployments ni privilegios excesivos en runtime?

## Contexto observado

El repositorio evolucionó de `SqliteLedger` (Etapa 2) a una arquitectura PostgreSQL en Neon (Etapa 3) regida por `ADR-ORCH-008`, `ADR-ORCH-010`, `ADR-ORCH-025` y `ADR-ORCH-027`:

- **Ledger conversacional (`modules/conversation/adapters/persistence/postgres/`):**
  - Esquema en `migrations/postgres/001..007`: tablas de `inbox_events`, `conversations`, `turns`, `outcomes`, `deliveries`, `dispatcher_claims` y `restore_audit`.
  - Row-Level Security (`002_e3_h1_rls.sql`) obligatoria por `deployment_id` y `tenant_id` establecida mediante `SET LOCAL` dentro de cada transacción.
  - Leases con `claim_generation` monótona (fencing en `003`, `004` y `006`) que impiden doble commit cuando un worker pierde su lease.
  - Pool compartido acotado en `foundation/pg_pool.py` (`PooledConnections`, `max_size=4`).
- **Knowledge Base / RAG (`modules/knowledge/`):**
  - Regla de aislamiento físico/lógico (`ADR-ORCH-010`): una base de datos Knowledge por `deployment_id` con `pgvector` (`vector(384)` en `migrations/knowledge/001_knowledge_schema.sql` e índice HNSW opcional en `002_hnsw_opt_in.sql`).
  - Versionado por generaciones (`knowledge_generations`, `knowledge_sources`, `knowledge_chunks`): solo la generación `ACTIVE` es consultable; la revocación o reingesta es atómica e idempotente.
  - Ingesta desde Google Drive (`modules/knowledge/application/drive_ingest.py` y `adapters/drive_http.py`) con service account de solo lectura y embeddings `text-embedding-3-small` (`384` dimensiones) acotados por presupuesto SQLite durable.

## Hallazgos y fuentes primarias

1. **Separación de roles SQL (`ADR-ORCH-027`):** los roles creados por API de Neon poseen `BYPASSRLS` por defecto. Se reemplazaron por roles SQL explícitos (`incubia_runtime` e `incubia_migrator` en el ledger; `incubia_kb_runtime`, `incubia_kb_ingestor` e `incubia_kb_migrator` en Knowledge) con `NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`.
2. **Validación fail-closed de DSN (`runtime_dsn.py`):** el resolver rechaza en el arranque cualquier DSN de runtime que no use host `*.neon.tech`, endpoint `-pooler`, `sslmode=require` o el usuario `incubia_kb_runtime`.
3. **Evidencia verificada en campañas E3-1, E3-2 y E3-4:**
   - `E3-1` (`evals/results/e3-1-campaign-2026-10-13-final.json`): 27/27 pruebas offline, Compose y 8/8 en Neon; restore M2 idempotente con RPO `2,12 s` y RTO `4,88 s`.
   - `E3-2` (`evals/results/e3-2-campaign-2026-10-15-local.json`): aislamiento entre dos tenants/actores, revocación y RLS 9/9 en Neon.
   - `E3-4` (`evals/results/e3-4-neon-local-20261024T034222Z.json` y `e3-4-g6-neon-local-20261024T034222Z.json`): recall@5 `1,00`, abstención `1,00`, `p95 = 0,592 s` con pool y cero fugas entre deployments.

Fuentes primarias:
- `docs/adr/ADR-ORCH-008-CONVERSATION-STATE-PERSISTENCE.md`
- `docs/adr/ADR-ORCH-010-RAG-VECTOR-STORE.md`
- `docs/adr/ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md`
- `docs/adr/ADR-ORCH-027-NEON-ROLE-PROVISIONING.md`
- `docs/roadmap/etapa-3/VERIFICACION.md`

## Alternativas evaluadas

1. **Neon PostgreSQL con RLS para Ledger + Base separada por deployment con `pgvector` para Knowledge:** unifica proveedor gestionado, reduce infraestructura adicional y garantiza aislamiento fuerte.
2. **Motor vectorial dedicado externo (Qdrant/Pinecone):** descartado en Etapa 3 (`ADR-ORCH-010`) por añadir otro sistema de credenciales, backups y red sin necesidad para el volumen actual.
3. **Compartir una sola tabla Knowledge multi-deployment solo con filtro en aplicación:** descartado por mayor superficie de fuga ante errores de consulta vectorial o índices HNSW.

## Recomendación

Mantener la **Alternativa 1**, integrando `compose_incubialab_retrieval` y `PostgresLedger` en el entrypoint productivo del VPS, completando el procedimiento de backup/restore para las tablas de Knowledge y auditoría (`ADR-ORCH-024`) y resolviendo los pendientes de corpus Drive registrados en `TODOS.md`.

## Beneficios

Enlazar: [[Persistencia y RAG en Neon - beneficios]]

## Contras y riesgos

Enlazar: [[Persistencia y RAG en Neon - contras y riesgos]]

## Decisión

Enlazar: [[Persistencia y RAG en Neon - decisión]]

## Estado de implementación

Enlazar: [[Persistencia y RAG en Neon - estado de implementación]]
