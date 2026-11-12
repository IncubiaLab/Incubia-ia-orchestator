---
tipo: implementacion
tema: Rollout y validación VPS P4-P5
estado: implementado
fecha: 2026-11-11
---

# Estado de Implementación: Rollout y Validación en VPS Staging (P4-P5)

## Componentes implementados y activos en el VPS
- **Contenedor Orchestrator Staging:** Contenedor `orchestrator-staging` en ejecución sobre Docker en el VPS `2.24.201.39`, conectado a la red `web`, corriendo como usuario no-root UID `10001`, con `/data` montado y healthcheck automático activo.
- **Reverse Proxy Caddy:** Enrutamiento configurado en `/opt/incubia/proxy/Caddyfile` para `agent-staging.incubialab.com` con `reverse_proxy orchestrator-staging:8080` y `flush_interval -1`.
- **Base de Datos y Migraciones:** 8 migraciones de esquema completadas en PostgreSQL Neon con tablas creadas y roles `incubia_runtime` e `incubia_migrator` verificados.
- **Manejo de Conexiones HTTP:** Cierre y drenado de conexiones seguras ante errores (`401`, `400`) implementado en `src/incubia_orchestrator/interfaces/http/service.py`.
- **Suite de Pruebas de Humo E2E:** `tests/smoke/test_vps_staging.py` creado y validado al 100%.

## Evidencia de ejecución
1. **Llamadas HTTP públicas sobre TLS:**
   - `curl https://agent-staging.incubialab.com/healthz` → `200 OK {"status":"ok"}`
   - `curl https://agent-staging.incubialab.com/readyz` → `200 OK {"status":"ready"}`
   - `curl https://agent-staging.incubialab.com/metrics` → Métricas consolidadas activas.
2. **Suite de humo automatizada:**
   - 8 gates evaluados con éxito: health, ready, 401 sin token, 401 con token inválido, execution 200 con respuesta LLM real, replay de idempotencia sin re-ejecución, segundo turno multivuelta con retención de contexto, streaming SSE Orbit con eventos `delta` y `done`, y reinicio de contenedor preservando el estado conversacional y de auditoría.
3. **Persistencia en Neon confirmada:**
   - Filas registradas durablemente en `audit_events`, `inbox_events` y `conversations`.

## Bloqueos abiertos
- Ninguno para P4 y P5. Las fases P0, P1, P2, P3, P4 y P5 están completamente cerradas y operativas en el VPS.

## Enlaces
- Investigación: [[Investigacion - rollout en VPS staging y validacion funcional E2E P4-P5]]
- Beneficios: [[Rollout y validación VPS P4-P5 - beneficios]]
- Contras y riesgos: [[Rollout y validación VPS P4-P5 - contras y riesgos]]
- Decisión: [[Rollout y validación VPS P4-P5 - decisión]]
