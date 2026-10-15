# Progreso — etapa 3

Fecha de actualización: 2026-10-13. **Implementación E3 iniciada; E3-D0-L acreditado y M3 de H1 listo para decisión.** Los gates arquitectónicos permanecen pendientes hasta contar con su decisión formal.

| Preparación | Estado | Evidencia / pendiente |
| --- | --- | --- |
| E3-H1-N | Preparación lista; no es un gate | [Preflight](E3-H1-N-PREFLIGHT.md): rama, roles SQL mínimos, grants, DSNs locales mode `0600`, migraciones `001`–`006`, RLS/UoW, leases/fencing y dispatcher; la campaña Neon final pasó 8 checks. E3-1 está listo para decisión formal. |

| Pista preliminar | Estado | Evidencia / pendiente |
| --- | --- | --- |
| E3-D0-L | Implementado y acreditado | Docker Compose local de instancia única con PostgreSQL, migración separada, HTTP loopback y adapters deterministas. Smoke completo passed en `incubia-e3-d0-final` (52.569 s), incluyendo replay, reinicio, recovery, SIGTERM, usuario no-root, readiness y logs sin secretos. No cierra H1–H5 ni E3-0. |
| E3-D0-R | Diferido | Sólo tras H1–H4, presupuesto/credenciales autorizados y evidencia separada de Neon, pgvector, READ, LLM, audit y métricas. |

| Hito | Estado | Evidencia / pendiente |
| --- | --- | --- |
| H0 | En curso | ADR-008/019/020 Accepted; contratos de identidad/ledger y UoW SQLite iniciados en E3-02. Inventario, integración completa, SLO/responsables y cierre E2 B/C pendientes. |
| H1 | Listo para decisión E3-1 | M1 y M2 acreditados; M3 integrado passed offline, Compose y Neon. Falta registrar la decisión formal; `gate_closed=false`. |
| H2 | Pendiente | Contratos/tenancy diseñados; autorización/membresías pendientes. |
| H3 | Pendiente | Tooling diseñado; fuente READ real por seleccionar. |
| H4 | Pendiente | ADR-010 Accepted: pgvector/base por deployment; dataset, embeddings, ingestión y evidencia operativa pendientes. |
| H5 | Pendiente | SLO/operación/carga por acreditar. |
| H6 | Pendiente | Lead/case/evaluación/cierre por implementar. |

Baseline E2: Gate A cerrado en [VERIFICACION E2](../etapa-2/VERIFICACION.md); B en progreso y C pendiente. [Smoke real](../../../evals/results/e2-real-smoke-2026-10-06.md) acredita transporte/contador de una generación, sin cierre de calidad. CLI y adapter Telegram existen; funcionamiento parcial informado por el usuario no sustituye evidencia de piloto completo.

Primer incremento: E3-01 inventario y decisiones, seguido de E3-02 contratos/UoW; E3-03/04/05 tienen expediente técnico listo para decisión. No añadir tools/RAG a nodos concretos antes de definir sus puertos.

Plan de cierre H1: [H1-CIERRE.md](H1-CIERRE.md) fija tres milestones: M1
completa equivalencia, ownership y fencing; M2 implementa export/import,
restore y RPO/RTO; M3 ejecuta la campaña integrada y registra la decisión
E3-1. El gate permanece abierto hasta la decisión formal.

M3 (2026-10-13): se ejecutó [la campaña integrada](../../../evals/results/e3-1-campaign-2026-10-13-final.json).
Offline pasó (27/27), E3-D0-L Compose pasó y Neon pasó (8/8) en la rama
sintética. El runner produjo `ready_for_gate` y conserva `gate_closed=false`
hasta la decisión formal.

E3-D0-L (2026-10-13): se acreditaron imagen Python 3.12 multi-stage/no-root, Compose local con PostgreSQL/migrador/app, ledger PostgreSQL de commit atómico, HTTP loopback, scope sintético, health/readiness, recovery y script de humo. El loop se valida mediante solicitudes HTTP encadenadas: cada una genera `execution_id` nuevo, conserva `conversation_id`, puede tomar otra capability/perfil y termina en commit durable antes del siguiente turno. Scope sintético por configuración; payload sin `deployment_id`/`tenant_id`/`actor_id`; publicación sólo loopback. Smoke completo passed tras sincronizar la salida de `SIGTERM` y añadir la migración local `006_e3_d0_runtime_claims.sql`. Docker Compose no ratifica ADR-024 ni implica Kubernetes, réplicas, microservicios o un contenedor por moneda/eje/círculo.

E3-02 (2026-10-08): se añadieron `Principal`/membresía/binding confiable, `ConversationLedgerPort`, `ConversationCommit` y commit SQLite de turno, revisión, outcome, inbox y outbox en una transacción. Telegram usa el evento tipado y ya no lee `ledger._connection`. `python3 -m compileall` y smoke manual de los contratos pasaron; no existe `.venv` y el Python disponible no tiene `pytest`/`httpx`, por lo que la suite E2/E3 queda pendiente en el entorno reproducible.

E3-H1-N / E3-03/04/05 (2026-10-09/13 UTC): Neon CLI 8.3.3 confirmó proyecto/plan/región/versión y rama sintética temporal desde `production`; PITR observado 21600 s y TTL de siete días. Los roles API iniciales con `BYPASSRLS` se eliminaron sin grants/uso. Tras ratificar ADR-ORCH-027, provisioning SQL creó roles sin privilegios elevados ni membresía de owner; runtime tiene `USAGE` sin `CREATE`, migrador tiene DDL. La campaña final aplicó `001`–`006` y pasó 8/8 pruebas de TLS, permisos, RLS, UoW, competencia de leases, expiración/takeover, fencing y ownership del dispatcher. M2 restauró una fila por tabla, verificó preservación e idempotencia y midió RPO/RTO; M3 dejó el expediente `ready_for_gate` y `gate_closed=false` a la espera de decisión formal.

Actualizar cada tarea con fecha, commit, goal/gate, comandos, resultados y limitaciones. Un pendiente externo permanece abierto; el resto de trabajo independiente puede continuar.
