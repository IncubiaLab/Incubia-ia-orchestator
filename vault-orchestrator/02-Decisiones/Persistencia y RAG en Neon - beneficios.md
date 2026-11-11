# Persistencia y RAG en Neon — beneficios

Fecha: 2026-11-11.

- **Aislamiento de defensa en profundidad:** RLS transaccional con roles `NOBYPASSRLS` en el ledger conversacional y base de datos separada por deployment en Knowledge (`ADR-ORCH-010`, `ADR-ORCH-027`).
- **Prevención de doble efecto:** leases y `claim_generation` (fencing) garantizan que un worker lento u obsoleto no pueda comitear un turno ni duplicar envíos tras perder su lease.
- **Latencia controlada con pooling:** `PooledConnections` (`foundation/pg_pool.py`) y `KnowledgePools` reducen el `p95` de retrieval en Neon de `6,27 s` (conexión por consulta) a `0,592 s`.
- **Actualización atómica del índice RAG:** las generaciones (`ACTIVE` / `RETIRED`) permiten reingestar y revocar documentos sin dejar el índice en un estado intermedio inconsistente.
- **Mismo ecosistema operativo:** unifica persistencia relacional, auditoría G7 y búsqueda vectorial (`pgvector`) bajo Neon sin introducir motores adicionales (Redis/Qdrant) en Etapa 3.

[[01-Investigacion/Persistencia-y-RAG-Neon/Investigacion - persistencia y RAG en Neon]] · [[Persistencia y RAG en Neon - contras y riesgos]] · [[Persistencia y RAG en Neon - decisión]] · [[03-Implementacion/Persistencia y RAG en Neon - estado de implementación]]
