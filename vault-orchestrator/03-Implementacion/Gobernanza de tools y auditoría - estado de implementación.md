---
tipo: implementacion
estado: gate-e3-3-cerrado-gate-e3-5-en-borrador
fecha: 2026-11-11
---

# Gobernanza de tools y auditoría — estado de implementación

## Implementado y verificado

- ** Ejecución gobernada de tools READ (`E3-3` cerrado):** `ExecuteTool`, `CatalogHttpToolAdapter`, `OpenFoodFactsAdapter`, detección de credenciales revocadas, protección SSRF y sanitización de salidas en `src/incubia_orchestrator/modules/orchestration/`.
- **Auditoría G7 y telemetría (`E3-5` en borrador):** `PostgresAuditLog` (`migrations/postgres/008_e3_g7_audit.sql`), `SqliteAuditLog`, `HttpMetrics` (`foundation/telemetry.py`) y `AdmissionLimiter` (`foundation/limits.py`).
- **Suites de verificación:** `tests/unit/test_tool_discovery.py`, `tests/integration/test_read_tool.py`, `tests/integration/test_openfoodfacts_read.py`, `tests/unit/test_postgres_audit.py`, `tests/integration/neon/test_g7_audit.py`, `tests/integration/test_e3_faults.py` y `tests/integration/test_e3_shutdown.py`.

## Pendiente

- [ ] Conectar `PostgresAuditLog` y `AdmissionLimiter` (`foundation/limits.py`) en el *composition root* productivo que atienda las solicitudes HTTP en el VPS.
- [ ] Ejecutar la campaña integrada de `E3-5` (carga `>= 10 min`, fallos bajo carga contra Neon, SIGTERM y restore completo) para cerrar `E3-5`.

[[01-Investigacion/Gobernanza-tools-y-auditoria/Investigacion - gobernanza de tools y auditoría]] · [[Gobernanza de tools y auditoría - beneficios]] · [[Gobernanza de tools y auditoría - contras y riesgos]] · [[Gobernanza de tools y auditoría - decisión]]
