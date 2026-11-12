---
tipo: decision
tema: Rollout y validación VPS P4-P5
estado: aceptado
fecha: 2026-11-11
---

# Decisión sobre el Rollout y Validación en VPS Staging (P4-P5)

Se ratifica la arquitectura desplegada y validada en el VPS de pruebas (`hector@2.24.201.39`):
1. **Unidad de despliegue:** Orquestador completo empaquetado como contenedor Docker no-root (`incubia-orchestrator:staging`), enrutado exclusivamente por la red Docker `web` detrás de Caddy bajo `agent-staging.incubialab.com`.
2. **Esquema de datos:** Base Neon PostgreSQL con 8 migraciones aplicadas de forma secuencial (`001_e3_d0_ledger.sql` a `008_e3_g7_audit.sql`) y segregación estricta entre `incubia_migrator` (conexión directa) e `incubia_runtime` (conexión pooled, TLS obligatorio).
3. **Validación E2E:** Aprobación sin excepciones de los gates funcionales ejecutados por `tests/smoke/test_vps_staging.py`:
   - Endpoint `/healthz` y `/readyz` (fail-closed)
   - Autenticación bearer estricta (401 ante token faltante o inválido)
   - Procesamiento de turnos multivuelta y persistencia en `PostgresLedger`
   - Replay de idempotencia con retención de respuesta previa
   - Streaming SSE compatible con Orbit Gateway en `/v1/turns`
   - Tolerancia a reinicio del contenedor sin pérdida de contexto ni corrupción de estado.

## Enlaces
- Investigación: [[Investigacion - rollout en VPS staging y validacion funcional E2E P4-P5]]
- Beneficios: [[Rollout y validación VPS P4-P5 - beneficios]]
- Contras y riesgos: [[Rollout y validación VPS P4-P5 - contras y riesgos]]
- Estado de implementación: [[Rollout y validación VPS P4-P5 - estado de implementación]]
