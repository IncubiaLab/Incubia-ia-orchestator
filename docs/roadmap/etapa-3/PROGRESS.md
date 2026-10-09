# Progreso — etapa 3

Fecha: 2026-10-08. **Implementación E3 iniciada; E3-02 en curso.** Los gates permanecen pendientes hasta contar con su evidencia completa.

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

E3-02 (2026-10-08): se añadieron `Principal`/membresía/binding confiable, `ConversationLedgerPort`, `ConversationCommit` y commit SQLite de turno, revisión, outcome, inbox y outbox en una transacción. Telegram usa el evento tipado y ya no lee `ledger._connection`. `python3 -m compileall` y smoke manual de los contratos pasaron; no existe `.venv` y el Python disponible no tiene `pytest`/`httpx`, por lo que la suite E2/E3 queda pendiente en el entorno reproducible.

Actualizar cada tarea con fecha, commit, goal/gate, comandos, resultados y limitaciones. Un pendiente externo permanece abierto; el resto de trabajo independiente puede continuar.
