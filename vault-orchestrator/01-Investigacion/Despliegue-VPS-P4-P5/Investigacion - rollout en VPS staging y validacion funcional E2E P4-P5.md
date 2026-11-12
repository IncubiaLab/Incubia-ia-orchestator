---
tipo: investigacion
tema: Rollout en VPS staging y validacion funcional E2E P4-P5
estado: aceptado
fecha: 2026-11-11
---

# Rollout en VPS Staging y Validación Funcional E2E (Fases P4 y P5)

## Pregunta y alcance
¿Cómo desplegar de forma segura el orchestrator completo en el VPS de pruebas (`hector@2.24.201.39`), aplicar la secuencia completa de migraciones PostgreSQL hacia Neon con separación de roles, exponerlo mediante el reverse proxy Caddy con TLS automatizado bajo `agent-staging.incubialab.com`, y validar rigurosamente la resiliencia operativa, idempotencia, streaming SSE y persistencia multivuelta tras reinicio (P4 y P5)?

## Contexto observado en el código
- El host VPS cuenta con Caddy corriendo en la red Docker `web` exponiendo los puertos 80/443 con certificados TLS gestionados automáticamente por Let's Encrypt para `agent-staging.incubialab.com`.
- Se requiere conectar el contenedor `orchestrator-staging` a la red `web` interna sin exponer puertos hacia la interfaz pública del host.
- Las migraciones `001_e3_d0_ledger.sql` a `008_e3_g7_audit.sql` exigen un rol migrador (`incubia_migrator`) para DDL y la presencia de `incubia_runtime` (`NOBYPASSRLS`) en `pg_roles` para otorgar permisos mínimos de DML y USAGE según `ADR-ORCH-025` y `ADR-ORCH-027`.
- El servicio HTTP expone endpoints `/healthz`, `/readyz`, `/metrics`, `POST /v1/executions` (JSON) y `POST /v1/turns` (SSE Orbit).

## Hallazgos verificables
1. **Provisionamiento de identidades SQL en Neon:**
   - La base `neondb` en `ep-billowing-darkness-b5n9mqa1` fue configurada con `incubia_runtime` (conexión pooled `-pooler` con `sslmode=require`) e `incubia_migrator` (conexión directa sin `-pooler` con `sslmode=require`), garantizando el principio de menor privilegio y cumplimiento estricto de las directivas RLS.
2. **Ejecución de migraciones en VPS:**
   - El contenedor `migrate` ejecutó las 8 migraciones consecutivas (`001` a `008`), provisionando las tablas del ledger (`inbox_events`, `conversations`, `claims`, `deliveries`, `audit_events`), esquemas y funciones asociadas.
3. **Integración con Caddy:**
   - Se configuró `/opt/incubia/proxy/Caddyfile` dirigiendo `agent-staging.incubialab.com` a `http://orchestrator-staging:8080` con directiva `flush_interval -1` para evitar el almacenamiento en buffer de eventos SSE (`delta` y `done`).
4. **Verificación funcional integrada (Smoke E2E):**
   - Validación de rechazo `401 Unauthorized` ante peticiones sin token o con Bearer token inválido.
   - Procesamiento de turnos conversacionales reales con LLM OpenAI (`gpt-4o-mini`).
   - Replay de idempotencia verificado: peticiones repetidas con la misma `Idempotency-Key` devuelven el resultado previamente computado sin invocar al LLM.
   - Memoria conversacional durable en `PostgresLedger`: turnos sucesivos conservan el historial de la conversación.
   - Streaming SSE verificado en `POST /v1/turns`.
   - Reinicio del contenedor (`docker compose restart orchestrator`) con recuperación de estado y prosecución de la conversación sin pérdida de datos.

## Alternativas evaluadas
- **Exponer el puerto 8080 en el host del VPS:** Rechazado; rompe el modelo perimetral seguro. Caddy y el orchestrator residen en la red Docker bridge privada `web`.
- **Desplegar un mock o gateway sin estado:** Rechazado tajantemente por `ADR-ORCH-024` y `PLAN-VPS.md`; la unidad productiva es el orchestrator modular completo con su runtime y persistencia.

## Recomendación
Consolidar el rollout en VPS Staging como el baseline de ejecución productiva de la Etapa 3.

## Nodos de convergencia
- Beneficios: [[Rollout y validación VPS P4-P5 - beneficios]]
- Contras y riesgos: [[Rollout y validación VPS P4-P5 - contras y riesgos]]
- Decisión: [[Rollout y validación VPS P4-P5 - decisión]]
- Estado de implementación: [[Rollout y validación VPS P4-P5 - estado de implementación]]
