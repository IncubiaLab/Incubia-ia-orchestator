---
tipo: decision_beneficios
tema: Rollout y validación VPS P4-P5
estado: aceptado
fecha: 2026-11-11
---

# Beneficios del Rollout y Validación en VPS Staging (P4-P5)

1. **Aislamiento de red absoluto:** El contenedor del orchestrator no expone ningún puerto hacia la interfaz de red pública del host. Todo el tráfico externo atraviesa TLS gestionado por Caddy en la red Docker `web`.
2. **Segregación estricta de privilegios de base de datos:** El runtime opera con el rol no privilegiado `incubia_runtime` sujeto a RLS (`NOBYPASSRLS`), mientras que las migraciones son ejecutadas de manera aislada por el rol migrador `incubia_migrator` sobre endpoint directo.
3. **Streaming SSE optimizado:** La configuración de `flush_interval -1` en el proxy Caddy garantiza que los eventos SSE generados por `/v1/turns` se transmitan en tiempo real sin latencias artificiales de buffer.
4. **Resiliencia operativa comprobada:** La suite de pruebas de humo E2E (`tests/smoke/test_vps_staging.py`) demostró que tras el reinicio del contenedor, las conversaciones y auditorías persisten intactas en Neon PostgreSQL y las llamadas multivuelta retienen el historial completo.
5. **Independencia del PC de desarrollo:** El orchestrator vive y opera completamente en el entorno cloud VPS (`agent-staging.incubialab.com`), desacoplado de máquinas locales.

## Enlaces
- Investigación: [[Investigacion - rollout en VPS staging y validacion funcional E2E P4-P5]]
- Contras y riesgos: [[Rollout y validación VPS P4-P5 - contras y riesgos]]
- Decisión: [[Rollout y validación VPS P4-P5 - decisión]]
- Estado de implementación: [[Rollout y validación VPS P4-P5 - estado de implementación]]
