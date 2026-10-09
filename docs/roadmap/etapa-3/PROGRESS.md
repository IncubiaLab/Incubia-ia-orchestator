# Progreso — etapa 3

Fecha: 2026-10-08. **Implementación E3 iniciada; E3-02 en curso y E3-D0-L implementado a la espera de evidencia Compose.** Los gates arquitectónicos permanecen pendientes hasta contar con su evidencia completa.

| Pista preliminar | Estado | Evidencia / pendiente |
| --- | --- | --- |
| E3-D0-L | Implementación lista; evidencia Compose pendiente | Docker Compose local de instancia única con PostgreSQL, migración separada, HTTP loopback y adapters deterministas. `PYTHONPATH=. uv run --isolated --extra test --extra deployment pytest -q` pasó (59); falta ejecutar `scripts/e3/d0_smoke.sh` en host con Docker. No cierra H1–H5 ni E3-0. |
| E3-D0-R | Diferido | Sólo tras H1–H4, presupuesto/credenciales autorizados y evidencia separada de Neon, pgvector, READ, LLM, audit y métricas. |

| Hito | Estado | Evidencia / pendiente |
| --- | --- | --- |
| H0 | En curso | ADR-008/019/020 Accepted; contratos de identidad/ledger y UoW SQLite iniciados en E3-02. Inventario, integración completa, SLO/responsables y cierre E2 B/C pendientes. |
| H1 | Pendiente | Neon elegido por ADR-025; adapter/migraciones/restore sin implementar. |
| H2 | Pendiente | Contratos/tenancy diseñados; autorización/membresías pendientes. |
| H3 | Pendiente | Tooling diseñado; fuente READ real por seleccionar. |
| H4 | Pendiente | ADR-010 Accepted: pgvector/base por deployment; dataset, embeddings, ingestión y evidencia operativa pendientes. |
| H5 | Pendiente | SLO/operación/carga por acreditar. |
| H6 | Pendiente | Lead/case/evaluación/cierre por implementar. |

Baseline E2: Gate A cerrado en [VERIFICACION E2](../etapa-2/VERIFICACION.md); B en progreso y C pendiente. [Smoke real](../../../evals/results/e2-real-smoke-2026-10-06.md) acredita transporte/contador de una generación, sin cierre de calidad. CLI y adapter Telegram existen; funcionamiento parcial informado por el usuario no sustituye evidencia de piloto completo.

Primer incremento: E3-01 inventario y decisiones, seguido de E3-02 contratos/UoW y E3-03 PostgreSQL sintético. No añadir tools/RAG a nodos concretos antes de definir sus puertos.

E3-D0-L (2026-10-08): se implementaron imagen Python 3.12 multi-stage/no-root, Compose local con PostgreSQL/migrador/app, ledger PostgreSQL de commit atómico, HTTP loopback, scope sintético, health/readiness, recovery y script de humo. El loop se valida mediante solicitudes HTTP encadenadas: cada una genera `execution_id` nuevo, conserva `conversation_id`, puede tomar otra capability/perfil y termina en commit durable antes del siguiente turno. Scope sintético por configuración; payload sin `deployment_id`/`tenant_id`/`actor_id`; publicación sólo loopback. Se ejecutaron 59 pruebas offline, compilación, `uv lock --check`, parse YAML y smoke HTTP local; Docker no está instalado en este workspace, por lo que el gate D0-L y `scripts/e3/d0_smoke.sh` quedan pendientes de ejecutar. Docker Compose no ratifica ADR-024 ni implica Kubernetes, réplicas, microservicios o un contenedor por moneda/eje/círculo.

E3-02 (2026-10-08): se añadieron `Principal`/membresía/binding confiable, `ConversationLedgerPort`, `ConversationCommit` y commit SQLite de turno, revisión, outcome, inbox y outbox en una transacción. Telegram usa el evento tipado y ya no lee `ledger._connection`. `python3 -m compileall` y smoke manual de los contratos pasaron; no existe `.venv` y el Python disponible no tiene `pytest`/`httpx`, por lo que la suite E2/E3 queda pendiente en el entorno reproducible.

Actualizar cada tarea con fecha, commit, goal/gate, comandos, resultados y limitaciones. Un pendiente externo permanece abierto; el resto de trabajo independiente puede continuar.
