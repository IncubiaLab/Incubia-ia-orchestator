---
tipo: decision
estado: aceptada-en-planificacion
fecha: 2026-11-11
---

# Despliegue del orchestrator en VPS — decisión

Alcance ratificado en `docs/roadmap/etapa-3/PLAN-VPS.md` y `ADR-ORCH-024`:

1. **Unidad de despliegue:** Desplegar el **orchestrator completo** en el VPS usando una imagen contenedor Python 3.12 fijada por digest, usuario no-root (`10001:10001`), filesystem de solo lectura con `/data` persistente y `cap_drop: ALL`. La API HTTP es la frontera de acceso para los aplicativos consumidores; no se reduce el orchestrator a un gateway sin estado.
2. **Persistencia externa en Neon (`ADR-ORCH-025`, `ADR-ORCH-027`):** `PostgresLedger` y `PostgresAuditLog` operan sobre Neon mediante `DATABASE_URL` pooled con TLS y rol `incubia_runtime` (`NOBYPASSRLS`). Las migraciones (`001`–`008`) se ejecutan en un job separado previo al rollout con `INCUBIA_MIGRATION_DATABASE_URL` directa y rol `incubia_migrator`.
3. **Knowledge Base por deployment (`ADR-ORCH-010`):** El retrieval se conecta con `INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL` (`incubia_kb_runtime`, solo `SELECT`, pooled TLS) y la ingesta de corpus corre como job separado con `incubia_kb_ingestor`.
4. **Condiciones previas a tráfico productivo:** Resolver los 10 bloqueos verificados en `PLAN-VPS.md` (lockfile con `psycopg_pool`, cadena completa de migraciones, composición productiva unificada, cuotas operativas, alineación de `drain_seconds` con timeout LLM, `/readyz` real y proxy HTTPS con autenticación) y cerrar la evidencia pendiente del gate `E3-5`.

[[01-Investigacion/Despliegue-VPS/Investigacion - despliegue del orchestrator en VPS]] · [[Despliegue del orchestrator en VPS - beneficios]] · [[Despliegue del orchestrator en VPS - contras y riesgos]] · [[03-Implementacion/Despliegue del orchestrator en VPS - estado de implementación]]
