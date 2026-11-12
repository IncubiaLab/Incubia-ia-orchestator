---
tipo: investigacion
tema: Despliegue del orchestrator en VPS
estado: revisado
fecha: 2026-11-11
---

# Investigación — despliegue del orchestrator en VPS

## Pregunta y alcance

¿Cómo desplegar el **orchestrator completo** en un VPS como servicio autónomo accedido por API por los demás aplicativos (Orbit, canales y herramientas administrativas), cumpliendo `ADR-ORCH-024`, `ADR-ORCH-025`, `ADR-ORCH-027` y `docs/roadmap/etapa-3/PLAN-VPS.md`, sin reducir el sistema a un gateway sin estado ni depender del PC de desarrollo?

## Contexto observado (Mapa completo del runtime — Paso 1 de PLAN-VPS)

El repositorio implementa un monolito modular en Python 3.12 (`src/incubia_orchestrator/`) cuyos módulos de dominio y aplicación ya existen, pero están ensamblados en tres *composition roots* parciales y cuatro puntos de entrada independientes:

### 1. Módulos del sistema y responsabilidades

| Módulo (`src/incubia_orchestrator/`) | Capacidades implementadas | Estado en runtime |
| --- | --- | --- |
| `foundation/` | Contratos (`ExecutionScope`, `StartExecutionRequest`, `ExecutionOutcome`), `PooledConnections` (`psycopg_pool`), `Limits`/`AdmissionLimiter` (`config/e3/limits.example.yaml`), `HttpMetrics` | Implementado y probado en E3 |
| `modules/orchestration/` | `HandleMessage`, `HandleInbound`, `GroundedWorkflow`, `ExecuteTool`, `CapabilityResolver`, `ContextBuilder`, `LangGraphRuntimeAdapter` (`select_specialty` → `generate_response`), `OpenAILLM` + `MonthlyCallLimiter`, `CatalogHttpToolAdapter` y `OpenFoodFactsAdapter` | Dividido entre `compose_scoped` (LLM real sin ledger/RAG) y `D0Runtime` (ledger/audit con fakes) |
| `modules/conversation/` | `PostgresLedger` (inbox, conversations, turns, outcomes, deliveries, leases/fencing `001`–`007`), `SqliteLedger`, `TelegramRunner`, backup/restore (`h1_backup.py`) | `PostgresLedger` activo en HTTP D0; `SqliteLedger` en CLI `incubia-bot`; ausente en `orbit_gateway.py` |
| `modules/identity_tenant/` | `Principal`, `Membership`, bindings por canal, validación de scope y revocación | Integrado en `HandleInbound` y tests E3-2; `orbit_gateway.py` delega identidad al BFF |
| `modules/governance/` | `InProcessPolicyEngine` (`Authority` por `deployment_id`, `tenant_id`, `actor_id`), PEP de generación y tools | Activo en todos los composition roots |
| `modules/knowledge/` | `KnowledgePools` (`max_size=4`), resolver fail-closed de DSN (`runtime_dsn.py`), pgvector (`vector(384)`), `DriveSourceCatalog`, `drive_ingest.py`, `openai_embedding.py` con presupuesto durable | Compuesto en `bootstrap/knowledge_incubialab.py` y `e3_probe.py`; aún no conectado al entrypoint HTTP principal ni a `orbit_gateway.py` |
| `modules/audit/` | `PostgresAuditLog` (migración `008_e3_g7_audit.sql`, RLS por scope, fail-closed antes de I/O de tool, canario de secretos) y `SqliteAuditLog` | `PostgresAuditLog` en HTTP D0 (`INCUBIA_D0_AUDIT=postgres`); `SqliteAuditLog` en `e3_probe.py`; ausente en `orbit_gateway.py` |

### 2. Composition roots (`bootstrap/`) y entradas (`interfaces/`)

| Composition root / Entrada | Qué conecta hoy | Qué le falta para operación productiva en VPS |
| --- | --- | --- |
| `bootstrap/composition.py` (`compose`, `compose_scoped`) | `LangGraphRuntimeAdapter`, `InProcessPolicyEngine`, `OpenAILLM` o `FakeLLM`, `MonthlyCallLimiter` | No conecta `PostgresLedger`, `PostgresAuditLog`, `GroundedWorkflow`, `KnowledgePools` ni tools READ; aplica límites de prueba (`REAL_MAX_OUTPUT_TOKENS=128`, 20 llamadas/mes, 10 s entre llamadas). |
| `bootstrap/d0.py` + `interfaces/http/main.py` (`8080`) | `PostgresLedger`, `PostgresAuditLog`, `PooledConnections`, `AdmissionLimiter`, `HttpMetrics`, `DrainingHTTPServer` | Solo acepta `INCUBIA_D0_MODE=local`, scope sintético fijo por entorno, sin autenticación HTTP, y usa `FakeLLM`/tools fake. |
| `interfaces/http/orbit_gateway.py` (`8081`) | Bearer auth (`>=32` chars), validación de payload y evidencia de Orbit, `compose_scoped`, respuesta SSE (`delta`, `citation`, `done`) | No persiste turnos/outcomes en `PostgresLedger`, pasa historial vacío `()`, no registra en `PostgresAuditLog`, no consulta `KnowledgePools` propios de IncubiaLab y `/readyz` no verifica dependencias ni drenaje. |
| `interfaces/cli/bot.py` (`incubia-bot`) | `TelegramRunner`, long-polling, `SqliteLedger`, `compose_scoped` | Usa SQLite local en lugar de `PostgresLedger` y comparte el archivo de `MonthlyCallLimiter`. |
| `bootstrap/knowledge_incubialab.py` + `scripts/e3/ingest_drive_knowledge.py` | `KnowledgePools` (`incubia_kb_runtime`), ingesta Google Drive con service account y embeddings OpenAI | Job puntual separado; falta enlazar su puerto de retrieval con la entrada HTTP productiva del orchestrator. |

## Contraste actualizado para la ejecución — 2026-11-11

El [plan de ejecución P0–P7](../../../docs/roadmap/etapa-3/PLAN-DESPLIEGUE-VPS.md) revisó `main` (`5a7df31`). El lock de Docker sí contiene `psycopg` y `psycopg-binary`; falta `psycopg_pool`. La composición productiva completa, readiness del gateway, migraciones y despliegue siguen pendientes. La plantilla `.env.example` actual ya no contiene el patrón Telegram descrito en los hallazgos históricos. Los recursos propuestos abajo son estimaciones; el host asignado aún necesita inventario. El estado actualizado se registra en [[Despliegue del orchestrator en VPS - estado de implementación]] y el acceso en [[VPS de pruebas - acceso SSH]].

## Hallazgos y fuentes primarias (revisión histórica)

1. **Bloqueo de empaquetado Docker (`requirements.lock` vs `pyproject.toml`):** `Dockerfile` de E3-D0 instala `requirements.lock` y luego `pip install --no-deps .`. `requirements.lock` no incluye `psycopg` ni `psycopg_pool`, requeridos por `PooledConnections` en `foundation/pg_pool.py`.
2. **Desfase de ramas (`main` vs `feat/knowledge-base`):** la verificación de Etapa 3 (`38770ed`) quedó en `feat/knowledge-base` cuando en GitHub se hizo `Merge branch 'main' into feat/knowledge-base` (`a676e21`) en lugar de fusionar hacia `main`. Reconciliar `main` con `feat/knowledge-base` restablece toda la base E3 verificada.
3. **Cadena de migraciones incompleta en entrypoint Docker:** `interfaces/http/migrate.py` solo aplica `001` y `006`, dejando fuera `002` (RLS), `003`–`004` (claims/dispatcher), `005` (backup), `007` y `008` (auditoría G7), además de `migrations/knowledge/001..002`.
4. **Cuotas y timeouts:** `MonthlyCallLimiter` (20 llamadas/mes) y `REAL_MAX_OUTPUT_TOKENS=128` bloquean un piloto real multiusuario; `DrainingHTTPServer` (`drain_seconds=10`) es menor que el timeout LLM (`30–60 s`).
5. **Seguridad de configuración:** `.env.example` en `feat/knowledge-base` contenía un valor con formato de token de Telegram que debe mantenerse saneado como placeholder (`REPLACE_ME`).

Fuentes primarias:
- `docs/roadmap/etapa-3/PLAN-VPS.md`
- `docs/adr/ADR-ORCH-024-DEPLOYMENT-TOPOLOGY.md`
- `docs/adr/ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md`
- `docs/adr/ADR-ORCH-027-NEON-ROLE-PROVISIONING.md`
- [Neon connection pooling](https://neon.com/docs/connect/connection-pooling)
- [Docker Compose en producción](https://docs.docker.com/compose/how-tos/production/)

## Alternativas evaluadas

1. **Orchestrator completo en un contenedor VPS con Neon externo (Opción A de `ADR-ORCH-024`):** ejecuta la API autenticada del orchestrator, su runtime LangGraph, políticas, adaptadores de tools/retrieval y conexión pooled a Neon (`incubia_runtime` / `incubia_kb_runtime`), más un job one-shot de migración (`incubia_migrator` / `incubia_kb_migrator`) y trabajos puntuales de ingesta.
2. **Gateway ligero sin estado en contenedor (`orbit_gateway.py` aislado):** descarta el ledger, la auditoría G7, el historial canónico y el retrieval propio del orchestrator; contradice el alcance corregido en `PLAN-VPS.md`.
3. **N réplicas tras balanceador (Opción B de `ADR-ORCH-024`):** ruta de escalado prevista cuando se cumplan los disparadores medidos de latencia (`p95 > 5 s` por CPU/RAM), disponibilidad o rolling deploy.

## Recomendación

Adoptar la **Alternativa 1 (Opción A de `ADR-ORCH-024`)** sobre VPS inicial de **2 vCPU, 4 GB RAM y 40 GB SSD** tras proxy HTTPS reverso, unificando el empaquetado con `psycopg`/`psycopg_pool`, completando el job de migración (`001`–`008` + Knowledge) y componiendo en `bootstrap/` la entrada HTTP autenticada con `PostgresLedger`, `PostgresAuditLog`, `KnowledgePools` y cuotas operativas configurables.

## Beneficios

Enlazar: [[Despliegue del orchestrator en VPS - beneficios]]

## Contras y riesgos

Enlazar: [[Despliegue del orchestrator en VPS - contras y riesgos]]

## Decisión

Enlazar: [[Despliegue del orchestrator en VPS - decisión]]

## Estado de implementación

Enlazar: [[Despliegue del orchestrator en VPS - estado de implementación]]
