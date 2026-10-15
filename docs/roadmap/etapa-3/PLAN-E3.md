# Plan ejecutable — etapa 3

Estado: planificación en ejecución. Seguir [BASE](BASE.md), [GOALS](GOALS.md) y [GLOSARIO](GLOSARIO.md). Implementar un slice por tarea, mantener modo offline y registrar evidencia en [VERIFICACION](VERIFICACION.md). No hacer commits, despliegues ni cierre de issues automáticamente por seguir este documento. E3-D0 es una pista preliminar de Docker Compose y no sustituye el gate E3-0 ni las tareas H1–H5.

## Entorno de ejecución previsto

Python ≥3.12 según pyproject.toml. Usar el entorno del proyecto, por ejemplo `.venv/bin/python -m pytest <prueba> -q`, y CLI fake `.venv/bin/python -m incubia_orchestrator.interfaces.cli.main chat --fake` cuando exista `.venv`. Resolver la instalación según herramientas disponibles; no asumir un comando `python` global. Estos comandos son futuros, no se han ejecutado en la planificación.

Conservar red bloqueada en la suite offline. PostgreSQL local/Neon y proveedor real se prueban en suite o runner explícito con configuración sintética; nunca desbloquear toda la suite por defecto. Credenciales fuera de repo, logs y argumentos CLI. Seleccionar y fijar dependencias nuevas en la tarea que las requiere, tras consultar documentación oficial vigente.

## Tareas

## Plan acotado para cerrar H1

El cierre de H1 se ejecuta en tres milestones y está detallado en
[H1-CIERRE.md](H1-CIERRE.md). El orden obligatorio es: (M1) completar
E3-03/04 con ownership persistente y `UNKNOWN_EFFECT`; (M2) implementar
E3-05 con export/import, restore y RPO/RTO medidos en Neon; (M3) ejecutar la
campaña integrada y registrar la decisión E3-1. La preparación E3-H1-N y los
checks parciales no sustituyen esos milestones; la campaña integrada final ya
ejecutó M3 y dejó el expediente `ready_for_gate`.

<a id="e3-d0"></a>

### E3-D0 — Baseline de deployment Docker Compose

**Pista:** preliminar y paralela a H0–H5; no es E3-0. **Goals:** evidencia local acotada, sin cierre de G1–G9. **Dependencias:** contratos E3-02 disponibles cuando se integren; puede iniciar con adapters deterministas antes de Neon.

Crear una imagen Python 3.12 multi-stage, reproducible y sin secretos, que ejecute como usuario no-root y escriba logs sanitizados a stdout. Añadir Docker Compose con `postgres` local y volumen persistente, migrador one-shot con credenciales separadas y una sola `app` que espere DB saludable y migración completada. Publicar únicamente `127.0.0.1`; Compose es un baseline local de instancia única, no una decisión de Kubernetes, múltiples réplicas, microservicios ni aprobación de ADR-024.

Exponer `GET /healthz`, `GET /readyz` y `POST /v1/executions`. Readiness exige configuración válida, migraciones aplicadas y PostgreSQL accesible. El `POST` local sin autenticación sólo acepta mensaje y clave de conversación; rechaza `deployment_id`, `tenant_id` y `actor_id` de cliente, pues toma un scope sintético fijo de configuración. Debe quedar prohibido fuera de loopback, staging y producción.

El camino usa los puertos de conversación, policy, routing y runtime con LLM falso y seams deterministas sin I/O para tool/retrieval. Esos seams devuelven evidencia vacía y no implementan ni acreditan los contratos H3/H4 ni proveedores reales. Cada solicitud reserva/commitea inbox, revisión, turno, outcome y outbox en PostgreSQL; genera un `execution_id` nuevo y conserva el mismo `conversation_id` cuando el cliente encadena turnos. Un turno puede tomar otra capability/perfil, pero termina tras su commit: no hay bucles internos ilimitados ni un contenedor por moneda, eje o círculo.

**Archivos objetivo:** `Dockerfile; .dockerignore; compose.yaml; deploy/; migrations/postgres/; src/incubia_orchestrator/interfaces/http/; src/incubia_orchestrator/bootstrap/; tests/{unit,integration}/; scripts/e3/` según el slice implementado.

**Validación y salida E3-D0-L:** usar `docker compose --env-file deploy/e3-d0.env build` y `scripts/e3/d0_smoke.sh`; imagen/proceso no-root; readiness falla sin DB/schema y pasa tras preflight; tres solicitudes encadenadas conservan conversación, revisión e IDs y recorren ramas deterministas distintas; replay no duplica turno/outcome/entrega; reiniciar `app` conserva conversación; SIGTERM deja estado recuperable; logs/health no filtran secretos; y no hay red a LLM, Telegram, tools o Neon. Registrar artefacto y comandos en VERIFICACION. Esta salida no cierra H1–H5.

**E3-D0-R diferido:** sólo después de H1–H4, credenciales y presupuesto aprobados, reutilizar la imagen y contrato HTTP para Neon, pgvector, una READ y LLM reales. Registrar presupuesto, audit y métricas en evidencia independiente; su éxito no sustituye G2–G9 ni los gates E3-1…E3-5.

### E3-H1-N — Preparación inicial de Neon

**Pista:** infraestructura preparatoria de H1; no es un gate y no cierra E3-1. **Dependencias:** rama predeterminada sintética confirmada por el operador; ADR-ORCH-025 Accepted para Tier 3.

Preflight del proyecto Neon sin cambiar región/plan: registrar Project ID, rama origen, región, PostgreSQL, plan, compute/autoscaling y PITR. Crear `e3-h1-synthetic` desde el origen sintético con el TTL vigente de siete días; reutilizar `neondb` para Control Plane. No crear Knowledge/pgvector en H1. Preparar runtime pooled TLS y migrador directo, ambos en roles distintos; restringir DDL al migrador y negar ownership/`BYPASSRLS` al runtime. El tenant/deployment se establece por transacción.

La implementación inicial añade `deploy/e3-neon.env.example` sin secretos, un generador local de permisos `0600` y un runner opt-in separado del bloqueo offline general. El runner sólo acepta la rama `e3-h1-synthetic`, host Neon, rol runtime pooled y rol migrador directo. La suite Neon se marca explícitamente y no modifica el comportamiento de las pruebas offline.

**Decisión y resultado:** [ADR-ORCH-027](../../adr/ADR-ORCH-027-NEON-ROLE-PROVISIONING.md) fue ratificado y registrado en Linear. Los roles API iniciales con atributos excesivos se eliminaron sin uso; el provisioning SQL creó roles `NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`, con `CREATE` sólo para el migrador. Los DSNs quedaron en archivo local ignorado mode `0600`. La campaña final aplicó `001`–`006` y pasó 8/8 checks Neon; el restore con filas, import idempotente y RPO/RTO están acreditados en el artefacto M2. No degradar el aislamiento RLS a filtros de aplicación.

**Archivos objetivo:** `scripts/e3/neon_h1.py; scripts/e3/run_neon_h1.py; deploy/e3-neon.env.example; tests/integration/neon/; migrations/postgres/; docs/roadmap/etapa-3/{RUNBOOK,VERIFICACION,PROGRESS}.md`.

**Salida de preparación:** roles sin atributos privilegiados, permisos mínimos verificables, DSNs separados y no expuestos, TLS/endpoints confirmados y runner registrado. E3-H1-N por sí sola no acredita gates; la campaña M3 separa la evidencia de migración/RLS, dispatcher/fencing y backup/restore en E3-03/04/05. H1 queda listo para decisión, no cerrado automáticamente.

<a id="e3-01"></a>

### E3-01 — Inventario y decisiones

**Hito:** H0. **Goals:** G1/G9. **Dependencias:** —.

Revisar VERIFICACION E2, código y estados ADR en Linear; registrar cierre A/B/C, SLO, retención, región, responsables, proveedor READ y necesidades HTTP. Preparar config/e3/limits.example.yaml con schemas y límites sin secretos.

**Archivos objetivo:** `docs/roadmap/etapa-3/{PROGRESS,AUTOPLAN-REVIEW,LINEAR-ADR}.md; config/e3/limits.example.yaml`.

**Validación y salida:** Revisión del inventario: cada decisión tiene dueño, condición y evidencia. Presupuesto nulo bloquea red; no trasladar contador CLI. Gate E3-0 se cierra cuando también E3-02 y E2 A/B/C están acreditados.

<a id="e3-02"></a>

### E3-02 — Contratos de identidad y unidad de trabajo

**Hito:** H0. **Goals:** G1/G2/G3. **Dependencias:** 01.

Extraer LedgerPort de las operaciones SQLite usadas por runner; definir Principal, membresía, resolución scoped y UoW de Conversation. Adaptar SQLite al contrato preservando CLI y estados E2. Versionar errores/conflictos y transacción final.

**Archivos objetivo:** `modules/conversation/ports/ledger.py; modules/identity_tenant/{domain,ports,application}/; modules/conversation/adapters/persistence/sqlite_ledger.py; tests/unit/test_e3_contracts.py`.

**Validación y salida:** Round-trip/schema desconocido, scope falsificado, versión obsoleta, commit final atómico y regresión Gate A. Contratos no importan SDK/SQL/LangGraph.

<a id="e3-03"></a>

### E3-03 — PostgreSQL y migraciones

**Hito:** H1. **Goals:** G2/G3. **Dependencias:** 02.

Fijar driver `psycopg` según `requirements.lock`; crear adapter PostgreSQL con el mismo `ConversationLedgerPort`. E3-03 versiona el ledger de Conversation y aplica RLS scoped por deployment/tenant con contexto transaccional; la propiedad de `bindings`/`memberships` corresponde a Identity/Tenant y se implementa en E3-06, conforme ADR-ORCH-008. Runtime y migrador usan roles separados y pool acotado. Usar la rama/base preparada por E3-H1-N con provisioning ADR-ORCH-027.

**Archivos objetivo:** `modules/conversation/adapters/persistence/postgres/; modules/identity_tenant/adapters/persistence/; migrations/postgres/; bootstrap/composition.py; pyproject.toml; tests/integration/test_postgres_ledger.py`.

**Validación y salida:** Suite de contrato SQLite/PostgreSQL; upgrade desde esquema anterior, transacción fallida sin estado parcial, conexión reutilizada entre tenants sin contaminación. PostgreSQL temporal local primero; Neon sintético separado y explícito mediante `scripts/e3/run_neon_h1.py`. Estado: migraciones `001`/`002`, aislamiento RLS, commit/replay/rollback y primera generación de claims ejecutados en la rama sintética; ampliar equivalencia de contrato y fixtures/recuperación antes de declarar E3-03 completo.

<a id="e3-04"></a>

### E3-04 — Claims, fencing y outbox compartida

**Hito:** H1. **Goals:** G2. **Dependencias:** 03.

Implementar reservas exclusivas, serialización por conversación y commits con token de generación. Un consumidor Telegram por cuenta con dueño compartido; documentar transición de lock local a claim remoto. Conservar UNKNOWN_EFFECT y IDs lógicos.

**Estado acreditado para M3:** migraciones `003_e3_h1_claims.sql` y `004_e3_h1_dispatcher_claims.sql`, junto con los adapters SQLite/PostgreSQL, ofrecen leases por recurso, ownership de cuenta, reloj de base de datos, generaciones monotónicas, renew/release y commit que valida claims de evento + conversación. Las pruebas locales y la campaña Neon final acreditan dispatcher, takeover, fencing y `UNKNOWN_EFFECT`/`SENT`; el expediente E3-1 queda listo para decisión formal.

**Archivos objetivo:** `modules/conversation/application/dispatch.py; modules/conversation/adapters/persistence/postgres/claims.py; modules/conversation/adapters/channels/telegram/runner.py; tests/integration/test_postgres_claims.py`.

**Validación y salida:** Dos procesos compiten por mismo evento/conversación; solo dueño vigente compromete. Caída tras envío remoto sin commit produce UNKNOWN_EFFECT y cero reenvíos; SENT no reenvía. Reinicio no borra inbox/offset.

<a id="e3-05"></a>

### E3-05 — Migración y restore Neon

**Hito:** H1. **Goals:** G2/G9. **Dependencias:** 04.

Crear export/import scoped con manifest, hashes, conteos y versiones; proteger IDs, claves dedup y revisiones. Staging sintético, backup consistente, restore y reconciliación de outbox antes del cambio de autoridad. Ejecutar runbook.

**Estado de implementación:** `PostgresLedgerBackup` y `scripts/e3/h1_backup.py`
implementan export/import determinista, detección de conflictos, limpieza de
claims, reconciliación `SENDING` → `UNKNOWN_EFFECT` y reporte RPO/RTO. La
prueba Neon con filas y doble import pasó; la evidencia está en
[e3-h1-m2-neon-2026-10-10.json](../../../evals/results/e3-h1-m2-neon-2026-10-10.json).

**Archivos objetivo:** `scripts/e3/migrate_ledger.py; scripts/e3/reconcile_ledger.py; docs/roadmap/etapa-3/RUNBOOK.md; evals/results/e3-data-*.md`.

**Validación y salida:** Export SQLite→PostgreSQL idempotente, rechazo de hashes conflictivos y migración incompleta; restore y RPO/RTO medidos. Gate E3-1 requiere estas evidencias y aislamiento sobre Neon con rol runtime.

<a id="e3-06"></a>

### E3-06 — Identidad, membresías y policy

**Hito:** H2. **Goals:** G3. **Dependencias:** 02/03.

Resolver scope por binding administrado y membresía vigente; roles actor/operator/admin acotados por tenant. Revalidar antes de leer/escribir/entregar. Provisioning/revocación mediante comando administrativo; HTTP solo si D3 define proveedor y necesidad.

**Archivos objetivo:** `modules/identity_tenant/application/; modules/governance/adapters/policy/in_process/engine.py; interfaces/cli/tenant.py; bootstrap/composition.py; tests/integration/test_tenant_isolation.py`.

**Validación y salida:** Dos tenants × dos actores; suplantación, recurso ajeno, rol insuficiente, revocación entre encolado y entrega, cache stale y rol sin bypass. Gate E3-2 prueba repositorios y discovery fake; aislamiento retrieval se añade en E3-11.

<a id="e3-07"></a>

### E3-07 — Contratos Tool Registry y Discovery

**Hito:** H3. **Goals:** G4. **Dependencias:** 02/06.

Crear ToolDescriptor/Invocation/Result, registry in-process, discovery scoped y selección estable. Configuración por tenant habilita integración con credencial opaca. Seleccionar una fuente READ accesible y documentar fixture/red real.

**Archivos objetivo:** `modules/orchestration/domain/tools.py; modules/orchestration/ports/{tool_discovery,tool_executor}.py; modules/orchestration/adapters/tools/registry.py; config/e3/tools.example.yaml; tests/unit/test_tool_discovery.py`.

**Validación y salida:** Descriptor disabled/ajeno/incompatible excluido; versión/input inválido y candidatos vacíos seguros; agregar adapter no cambia routing/nodos. Selection no otorga autorización.

<a id="e3-08"></a>

### E3-08 — Tool Executor y adapter READ

**Hito:** H3. **Goals:** G4/G7. **Dependencias:** 07.

Autorizar por operación/recurso, ejecutar catalog.lookup fake/fixture/real mediante httpx existente; mapear errores/timeouts, limitar output y retries. Registrar tool_call_id, intentos y eventos. Mantener mutations desactivadas.

**Archivos objetivo:** `modules/orchestration/application/execute_tool.py; modules/orchestration/adapters/tools/catalog_http.py; modules/audit/{domain,ports,adapters}/; tests/integration/test_read_tool.py`.

**Validación y salida:** DENY/INDETERMINATE/REQUIRE_APPROVAL cero red; rate limit, credencial revocada, SSRF, JSON grande/inválido e injection seguros. Gate E3-3 incluye lectura real controlada y respuesta rastreable; fakes no cierran conexión externa.

<a id="e3-09"></a>

### E3-09 — Contratos Knowledge y dataset

**Hito:** H4. **Goals:** G5/G6. **Dependencias:** 02/06.

Crear Retrieval/Embedding/KnowledgeRepository y fuente/evidencia versionada; fake scoped. Dataset dev/val según KNOWLEDGE; corpus sintético de dos deployments, referencias relevantes y consultas sin respuesta.

**Archivos objetivo:** `modules/knowledge/{domain,ports}/; modules/knowledge/adapters/retrieval/fake.py; evals/e3/retrieval.jsonl; evals/e3/response_cases.jsonl; tests/unit/test_knowledge_contracts.py`.

**Validación y salida:** Source/version/deployment required, query/top_k/tokens limitados, fuente de otro deployment excluida y val congelado con hash; ≥60 consultas y ≥24 escenarios de calidad.

<a id="e3-10"></a>

### E3-10 — pgvector e ingestión

**Hito:** H4. **Goals:** G5. **Dependencias:** 09/03.

Implementar el adapter pgvector de ADR-010 por deployment; elegir embeddings/dimensión/model version, ingestión por hashes, generaciones y swap de índice activo. Acreditar búsqueda exacta y evaluar HNSW por feature flag, sin reabrir la selección de backend.

**Archivos objetivo:** `modules/knowledge/adapters/{embedding,persistence}/; modules/knowledge/application/ingest.py; interfaces/cli/knowledge.py; migrations/postgres/; docs/roadmap/etapa-3/AUTOPLAN-REVIEW.md`.

**Validación y salida:** Reingesta idempotente, generación parcial invisible, dimensión inválida, fallo embedding, source revocada, aislamiento entre deployments y borrar/reindex con lecturas. Llamadas reales solo con presupuesto eval-e3 configurado.

<a id="e3-11"></a>

### E3-11 — Respuesta combinada y contexto

**Hito:** H4. **Goals:** G5/G6. **Dependencias:** 08/10.

Application coordina tool READ y retrieval con contexto/perfil, límites de pasos y deadline. Integrar EvidenceItems a ContextBuilder y referencias públicas por ResponseContextPort. Runtime conecta servicios sin SDK ni adapters concretos.

**Archivos objetivo:** `modules/orchestration/application/context_builder.py; modules/orchestration/application/use_cases/handle_inbound.py; modules/conversation/application/response_context.py; modules/orchestration/adapters/runtime/langgraph/; tests/integration/test_grounded_conversation.py`.

**Validación y salida:** Datos ausentes/conflictivos→abstención/caso; injection no cambia permisos; referencias seguras y sin canarios internos. Gate E3-4 mide G5/G6 y repite pruebas cross-deployment sobre store real.

<a id="e3-12"></a>

### E3-12 — Auditoría, métricas y despliegue

**Hito:** H5. **Goals:** G7/G9. **Dependencias:** 04/08/11.

Persistir eventos propios de audit y emitir métricas scoped de latencia/costo/errores/saturación. E3-D0 puede haber acreditado una imagen única, health/readiness y shutdown local; H5 amplía esa base con telemetría, carga, autoridad y hosting decididos en D8. Añadir HTTP/worker únicamente si mediciones lo requieren; no interpretar Compose local como ratificación de topología productiva.

**Archivos objetivo:** `modules/audit/; foundation/telemetry.py; bootstrap/composition.py; deploy/; tests/integration/test_e3_shutdown.py`.

**Validación y salida:** Correlación completa de todos los casos; secretos canario ausentes; detener en procesamiento/envío conserva estados recuperables. Audit de policy/tool crítico debe persistirse antes de operación; si falla, bloquea. Exportador de métricas fallido no rompe commits.

<a id="e3-13"></a>

### E3-13 — Carga, fallos y operación

**Hito:** H5. **Goals:** G2/G3/G7/G9. **Dependencias:** 05/06/12.

Ejecutar campañas fake/local y staging sintético según GOALS; comparar sesiones activas vs requests en vuelo. Medir pool, latencias, CPU/memoria, colas, cuota y costos. Ensayar interrupción DB/proveedor, rollback, restore y shutdown.

**Archivos objetivo:** `scripts/e3/load.py; evals/results/e3-ops-*.md; docs/roadmap/etapa-3/RUNBOOK.md`.

**Validación y salida:** ≥10 min por perfil de carga acordado, muestras/semilla/RPS/concurrencia declaradas. Cero pérdida/duplicación lógica y fuga; SLO/RPO/RTO medidos. Gate E3-5 ratifica ADR-024 aplicable y límites publicados.

<a id="e3-14"></a>

### E3-14 — Leads y casos internos

**Hito:** H6. **Goals:** G8. **Dependencias:** 06/11.

Abrir Sales/Support con entidad/repositorio/casos de uso scoped. Lead exige consentimiento explícito y campos mínimos; fallback propone caso y persiste solo con regla autorizada. Deduplicar por execution_id + tipo lógico. No llamar CRM/helpdesk.

**Archivos objetivo:** `modules/sales/{domain,ports,application,adapters}/; modules/support/{domain,ports,application,adapters}/; migrations/postgres/; tests/integration/test_lead_case.py`.

**Validación y salida:** Replay→un registro, tenant/actor ajeno→deny, consentimiento ausente→sin lead, datos mínimos/redactados, revocación y retención. Un caso interno no acredita entrega humana externa.

<a id="e3-15"></a>

### E3-15 — Evaluación y cierre

**Hito:** H6. **Goals:** G1–G9. **Dependencias:** 13/14.

Ejecutar val retrieval y respuestas reales con eval-e3; rúbrica humana, matriz de fallos, latencias/tokens/costo. E2E Telegram/CLI con tool/retrieval y lead/case sintéticos. Consolidar gates/ADR/limitaciones y decisión release del responsable.

**Archivos objetivo:** `evals/run_e3.py; evals/results/e3-release-*.md; docs/roadmap/etapa-3/{VERIFICACION,PROGRESS,LINEAR-ADR}.md`.

**Validación y salida:** Cumplir GOALS con cero fallos críticos; config/model/source versions y hashes congelados. Gate E3-6 no se cierra con resultados parciales; autorización de despliegue/tráfico real se registra al final del expediente.
