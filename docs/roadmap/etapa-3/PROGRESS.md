# Progreso — etapa 3

Fecha de actualización: 2026-10-10. **Implementación E3 iniciada; E3-02 en curso y E3-D0-L implementado a la espera de evidencia Compose.** Los gates arquitectónicos permanecen pendientes hasta contar con su evidencia completa.

| Preparación | Estado | Evidencia / pendiente |
| --- | --- | --- |
| E3-H1-N | Preparación lista; no es un gate | [Preflight](E3-H1-N-PREFLIGHT.md): rama, roles SQL mínimos, grants, DSNs locales mode `0600`, migraciones `001`–`003`, RLS/UoW y leases/fencing iniciales; 6 checks Neon pasaron. E3-05 y E3-1 siguen abiertos. |

| Pista preliminar | Estado | Evidencia / pendiente |
| --- | --- | --- |
| E3-D0-L | Implementación lista; evidencia Compose pendiente | Docker Compose local de instancia única con PostgreSQL, migración separada, HTTP loopback y adapters deterministas. `PYTHONPATH=. uv run --isolated --extra test --extra deployment pytest -q` pasó (59); falta ejecutar `scripts/e3/d0_smoke.sh` en host con Docker. No cierra H1–H5 ni E3-0. |
| E3-D0-R | Diferido | Sólo tras H1–H4, presupuesto/credenciales autorizados y evidencia separada de Neon, pgvector, READ, LLM, audit y métricas. |

| Hito | Estado | Evidencia / pendiente |
| --- | --- | --- |
| H0 | En curso | ADR-008/019/020 Accepted; contratos de identidad/ledger y UoW SQLite iniciados en E3-02. Inventario, integración completa, SLO/responsables y cierre E2 B/C pendientes. |
| H1 | En progreso | E3-03 implementa ledger PostgreSQL/RLS; E3-04 ya tiene leases de evento/conversación, generación y commit fenced, pero falta ownership Telegram/outbox y UNKNOWN_EFFECT. E3-05, equivalencia completa y E3-1 pendientes. |
| H2 | Pendiente | Contratos/tenancy diseñados; autorización/membresías pendientes. |
| H3 | Pendiente | Tooling diseñado; fuente READ real por seleccionar. |
| H4 | Pendiente | ADR-010 Accepted: pgvector/base por deployment; dataset, embeddings, ingestión y evidencia operativa pendientes. |
| H5 | Pendiente | SLO/operación/carga por acreditar. |
| H6 | Pendiente | Lead/case/evaluación/cierre por implementar. |

Baseline E2: Gate A cerrado en [VERIFICACION E2](../etapa-2/VERIFICACION.md); B en progreso y C pendiente. [Smoke real](../../../evals/results/e2-real-smoke-2026-10-06.md) acredita transporte/contador de una generación, sin cierre de calidad. CLI y adapter Telegram existen; funcionamiento parcial informado por el usuario no sustituye evidencia de piloto completo.

Primer incremento: E3-01 inventario y decisiones, seguido de E3-02 contratos/UoW; E3-03 PostgreSQL sintético está en curso. No añadir tools/RAG a nodos concretos antes de definir sus puertos.

E3-D0-L (2026-10-08): se implementaron imagen Python 3.12 multi-stage/no-root, Compose local con PostgreSQL/migrador/app, ledger PostgreSQL de commit atómico, HTTP loopback, scope sintético, health/readiness, recovery y script de humo. El loop se valida mediante solicitudes HTTP encadenadas: cada una genera `execution_id` nuevo, conserva `conversation_id`, puede tomar otra capability/perfil y termina en commit durable antes del siguiente turno. Scope sintético por configuración; payload sin `deployment_id`/`tenant_id`/`actor_id`; publicación sólo loopback. Se ejecutaron 59 pruebas offline, compilación, `uv lock --check`, parse YAML y smoke HTTP local; Docker no está instalado en este workspace, por lo que el gate D0-L y `scripts/e3/d0_smoke.sh` quedan pendientes de ejecutar. Docker Compose no ratifica ADR-024 ni implica Kubernetes, réplicas, microservicios o un contenedor por moneda/eje/círculo.

E3-02 (2026-10-08): se añadieron `Principal`/membresía/binding confiable, `ConversationLedgerPort`, `ConversationCommit` y commit SQLite de turno, revisión, outcome, inbox y outbox en una transacción. Telegram usa el evento tipado y ya no lee `ledger._connection`. `python3 -m compileall` y smoke manual de los contratos pasaron; no existe `.venv` y el Python disponible no tiene `pytest`/`httpx`, por lo que la suite E2/E3 queda pendiente en el entorno reproducible.

E3-H1-N / E3-03/04 parcial (2026-10-09/10 UTC): Neon CLI 8.3.3 confirmó proyecto/plan/región/versión y rama sintética temporal desde `production`; PITR observado 21600 s y TTL de siete días. Los roles API iniciales con `BYPASSRLS` se eliminaron sin grants/uso. Tras ratificar ADR-ORCH-027, provisioning SQL creó roles sin privilegios elevados ni membresía de owner; runtime tiene `USAGE` sin `CREATE`, migrador tiene DDL. DSNs locales ignorados, mode `0600`. Se aplicaron migraciones `001`–`003`; 6 pruebas Neon acreditan TLS, permisos, RLS, UoW, competencia de leases, expiración/takeover y rechazo de commits con fencing obsoleto. Falta account ownership/dispatcher, UNKNOWN_EFFECT, import/restore y equivalencia completa SQLite/PostgreSQL; no cierra E3-1.

Actualizar cada tarea con fecha, commit, goal/gate, comandos, resultados y limitaciones. Un pendiente externo permanece abierto; el resto de trabajo independiente puede continuar.
