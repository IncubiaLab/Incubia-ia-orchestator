---
tipo: investigacion
tema: Gobernanza de tools y auditoría
estado: revisado
fecha: 2026-11-11
---

# Investigación — gobernanza de tools y auditoría

## Pregunta y alcance

¿Cómo ejecutar herramientas externas de lectura (`READ`), controlar reintentos y cuotas operativas, y auditar el 100 % de las decisiones de política, ejecuciones de herramientas, retrieval y outcomes sin filtrar secretos ni permitir ejecuciones no autorizadas?

## Contexto observado

El diseño e implementación en Etapa 3 (`ADR-ORCH-014`, `ADR-ORCH-015`, `ADR-ORCH-026`, `docs/roadmap/etapa-3/TOOLING.md`) establece tres pilares en el código:

1. **Descubrimiento y ejecución gobernada de Tools (`modules/orchestration/domain/tools.py`, `application/execute_tool.py`, `adapters/tools/`):**
   - Toda herramienta se declara mediante descriptor tipado con `mutability` (`READ` únicamente habilitado en E3; `WRITE` rechazado por invariante), `scope`, `timeout`, `max_response_bytes` y esquema de entrada/salida.
   - `ExecuteTool` actúa como Policy Enforcement Point (PEP): evalúa la política (`InProcessPolicyEngine`), valida credenciales activas, registra el intento en el puerto de auditoría **antes** de realizar I/O de red (modo *fail-closed*), impone protección anti-SSRF y marca la salida como evidencia no confiable (`untrusted`).
   - Adaptador real verificado: `OpenFoodFactsAdapter` (`adapters/tools/openfoodfacts.py`) sobre Open Food Facts v3.
2. **Auditoría durable G7 (`modules/audit/adapters/postgres.py`, `migrations/postgres/008_e3_g7_audit.sql`):**
   - Tabla `audit_events` protegida con RLS por `deployment_id` y `tenant_id`; el rol `incubia_runtime` solo posee `INSERT` y `SELECT` (sin `UPDATE`/`DELETE`).
   - Correlaciona eventos de `policy`, `tool`, `retrieval` y `outcome` por `execution_id` y rechaza mediante canario cualquier intento de persistir secretos (`sk-`, `Bearer`, DSNs).
3. **Límites, admisión y reintentos (`foundation/limits.py`, `foundation/telemetry.py`, `config/e3/limits.example.yaml`):**
   - `load_runtime_limits()` exige `status: ratified` y valores positivos (*fail-closed*).
   - `ADR-ORCH-015` separa errores transitorios reintentables (con backoff acotado y solo en lecturas idempotentes) de `PROVIDER_QUOTA`, denegaciones de política o efectos de envío inciertos (`UNKNOWN_EFFECT`), los cuales nunca se reintentan automáticamente.

## Hallazgos y fuentes primarias

- **Gate `E3-3` cerrado (2026-10-23):** `evals/results/e3-3-campaign-2026-10-24.json` acreditó lectura real controlada (`ALLOW` → `SUCCESS`) y cuatro rutas denegadas (`DENY`, credencial revocada, mutación, fuera de scope) con **cero llamadas HTTP** al proveedor y auditoría correlacionada.
- **Gate `E3-5` en borrador abierto:** la mecánica de auditoría durable, métricas (`HttpMetrics`), drenaje HTTP (`DrainingHTTPServer`), inyección de fallos (`tests/integration/test_e3_faults.py`) y límites ratificados (`p95 <= 5 s`, `RPO <= 12 h`, `RTO <= 1 h`) está implementada y probada en suite offline y Neon 10/10, quedando pendiente únicamente la campaña de carga integrada de 10 minutos sobre la plataforma final.
- **Hallazgo abierto en degradación de embeddings:** en `tests/integration/test_e3_faults.py`, la degradación automática a abstención ante caída del proveedor de embeddings se mantiene vigilada para la campaña integrada de `E3-5`.

Fuentes primarias:
- `docs/adr/ADR-ORCH-014-AUDIT.md`
- `docs/adr/ADR-ORCH-015-RETRIES.md`
- `docs/adr/ADR-ORCH-026-CONTEXT-ARTIFACT-CACHE.md`
- `docs/roadmap/etapa-3/TOOLING.md`
- `docs/roadmap/etapa-3/VERIFICACION.md`

## Alternativas evaluadas

1. **PEP en `ExecuteTool` + auditoría PostgreSQL *fail-closed* con RLS + límites YAML ratificados:** garantiza trazabilidad obligatoria antes de cualquier llamada externa y aislamiento por tenant.
2. **Auditoría asíncrona *best-effort* en memoria/archivos:** descartada para `G7` porque un fallo del proceso permitiría ejecutar herramientas externas sin dejar rastro auditable.

## Recomendación

Conservar la **Alternativa 1** y conectarla al entrypoint productivo en VPS para que tanto las solicitudes de Orbit como las de otros canales pasen por los límites ratificados (`foundation/limits.py`) y la auditoría durable (`PostgresAuditLog`).

## Beneficios

Enlazar: [[Gobernanza de tools y auditoría - beneficios]]

## Contras y riesgos

Enlazar: [[Gobernanza de tools y auditoría - contras y riesgos]]

## Decisión

Enlazar: [[Gobernanza de tools y auditoría - decisión]]

## Estado de implementación

Enlazar: [[Gobernanza de tools y auditoría - estado de implementación]]
