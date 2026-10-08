# Plan ejecutable — etapa 3

Estado: planificación completa, ejecución pendiente. Seguir [BASE](BASE.md), [GOALS](GOALS.md) y [GLOSARIO](GLOSARIO.md). Implementar un slice por tarea, mantener modo offline y registrar evidencia en [VERIFICACION](VERIFICACION.md). No hacer commits, despliegues ni cierre de issues automáticamente por seguir este documento.

## Entorno de ejecución previsto

Python ≥3.12 según pyproject.toml. Usar el entorno del proyecto, por ejemplo `.venv/bin/python -m pytest <prueba> -q`, y CLI fake `.venv/bin/python -m incubia_orchestrator.interfaces.cli.main chat --fake` cuando exista `.venv`. Resolver la instalación según herramientas disponibles; no asumir un comando `python` global. Estos comandos son futuros, no se han ejecutado en la planificación.

Conservar red bloqueada en la suite offline. PostgreSQL local/Neon y proveedor real se prueban en suite o runner explícito con configuración sintética; nunca desbloquear toda la suite por defecto. Credenciales fuera de repo, logs y argumentos CLI. Seleccionar y fijar dependencias nuevas en la tarea que las requiere, tras consultar documentación oficial vigente.

## Tareas

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

Seleccionar driver/herramienta de migración versionados compatibles con Python del proyecto; crear adapter PostgreSQL con mismo LedgerPort. Migraciones iniciales incluyen tenants/memberships/bindings y tablas de Conversation; roles runtime/migrador, RLS y pool. Registrar región/plan Neon antes de staging.

**Archivos objetivo:** `modules/conversation/adapters/persistence/postgres/; modules/identity_tenant/adapters/persistence/; migrations/postgres/; bootstrap/composition.py; pyproject.toml; tests/integration/test_postgres_ledger.py`.

**Validación y salida:** Misma suite de contrato SQLite/PostgreSQL; upgrade desde esquema anterior, transacción fallida sin estado parcial, conexión reutilizada entre tenants sin contaminación. PostgreSQL temporal local primero; Neon sintético separado.

<a id="e3-04"></a>

### E3-04 — Claims, fencing y outbox compartida

**Hito:** H1. **Goals:** G2. **Dependencias:** 03.

Implementar reservas exclusivas, serialización por conversación y commits con token de generación. Un consumidor Telegram por cuenta con dueño compartido; documentar transición de lock local a claim remoto. Conservar UNKNOWN_EFFECT y IDs lógicos.

**Archivos objetivo:** `modules/conversation/application/dispatch.py; modules/conversation/adapters/persistence/postgres/claims.py; modules/conversation/adapters/channels/telegram/runner.py; tests/integration/test_postgres_claims.py`.

**Validación y salida:** Dos procesos compiten por mismo evento/conversación; solo dueño vigente compromete. Caída tras envío remoto sin commit produce UNKNOWN_EFFECT y cero reenvíos; SENT no reenvía. Reinicio no borra inbox/offset.

<a id="e3-05"></a>

### E3-05 — Migración y restore Neon

**Hito:** H1. **Goals:** G2/G9. **Dependencias:** 04.

Crear export/import scoped con manifest, hashes, conteos y versiones; proteger IDs, claves dedup y revisiones. Staging sintético, backup consistente, restore y reconciliación de outbox antes del cambio de autoridad. Ejecutar runbook.

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

Crear Retrieval/Embedding/KnowledgeRepository y fuente/evidencia versionada; fake scoped. Dataset dev/val según KNOWLEDGE; corpus sintético de dos tenants, referencias relevantes y consultas sin respuesta.

**Archivos objetivo:** `modules/knowledge/{domain,ports}/; modules/knowledge/adapters/retrieval/fake.py; evals/e3/retrieval.jsonl; evals/e3/response_cases.jsonl; tests/unit/test_knowledge_contracts.py`.

**Validación y salida:** Source/version/tenant required, query/top_k/tokens limitados, fuente ajena excluida y val congelado con hash; ≥60 consultas y ≥24 escenarios de calidad.

<a id="e3-10"></a>

### E3-10 — Decisión vectorial e ingestión

**Hito:** H4. **Goals:** G5. **Dependencias:** 09/03.

Comparar candidato pgvector en PostgreSQL y alternativa de store usando pequeño benchmark/documentación vigente; ratificar ADR-010 aplicable y construir solo el elegido. Elegir embeddings/dimensión/model version, ingestión por hashes, versiones y swap de índice activo.

**Archivos objetivo:** `modules/knowledge/adapters/{embedding,persistence}/; modules/knowledge/application/ingest.py; interfaces/cli/knowledge.py; migrations/postgres/; docs/roadmap/etapa-3/AUTOPLAN-REVIEW.md`.

**Validación y salida:** Reingesta idempotente, índice parcial invisible, dimensión inválida, fallo embedding, source revocada y borrar/reindex con lecturas. Llamadas reales solo con presupuesto eval-e3 configurado.

<a id="e3-11"></a>

### E3-11 — Respuesta combinada y contexto

**Hito:** H4. **Goals:** G5/G6. **Dependencias:** 08/10.

Application coordina tool READ y retrieval con contexto/perfil, límites de pasos y deadline. Integrar EvidenceItems a ContextBuilder y referencias públicas por ResponseContextPort. Runtime conecta servicios sin SDK ni adapters concretos.

**Archivos objetivo:** `modules/orchestration/application/context_builder.py; modules/orchestration/application/use_cases/handle_inbound.py; modules/conversation/application/response_context.py; modules/orchestration/adapters/runtime/langgraph/; tests/integration/test_grounded_conversation.py`.

**Validación y salida:** Datos ausentes/conflictivos→abstención/caso; injection no cambia permisos; referencias seguras y sin canarios internos. Gate E3-4 mide G5/G6 y repite pruebas tenant sobre store real.

<a id="e3-12"></a>

### E3-12 — Auditoría, métricas y despliegue

**Hito:** H5. **Goals:** G7/G9. **Dependencias:** 04/08/11.

Persistir eventos propios de audit y emitir métricas scoped de latencia/costo/errores/saturación. Imagen app única y health/readiness/graceful shutdown; telemetría concreta y hosting se registran en D8, no se eligen anticipadamente. Añadir HTTP/worker únicamente si mediciones lo requieren.

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
