# Revisión del plan — decisiones y gates

Fecha: 2026-10-07. Esta planificación no ratifica ADR globales abiertos. Una resolución local explicita alcance y evidencia antes de avanzar.

| Decisión | Propuesta / estado | Resolución necesaria |
| --- | --- | --- |
| D1 Persistencia | Neon seleccionado en ADR-025; implementación pendiente | Driver/migraciones, región, plan operativo, pool y restore antes de E3-1. |
| D2 Estado canónico | ADR-008 Accepted: Conversation autoridad; runtime privado | Implementar UoW, IDs y recovery en E3-02; ADR-019 conserva la frontera GraphState. |
| D3 Identidad | Bindings de canal + membresías server-side | Elegir proveedor auth solo si se habilita HTTP; no construir auth casero; E3-0/2. |
| D4 Concurrencia | Claims/fencing y un consumidor por bot; workers condicionados a evidencia | Reservas multi-proceso y recovery E3-04/05. |
| D5 Integración | Una fuente READ por Tool Layer | Elegir sistema/credenciales/fixture con responsable en E3-07. |
| D6 RAG | ADR-010 Accepted: Neon/PostgreSQL + pgvector, una base por deployment | Fake primero; E3-10 fija embeddings/dimensión y acredita búsqueda exacta/HNSW, ingestión y operación. |
| D7 Efectos | Mutations externas apagadas; leads/cases internos autorizados | No exigir ADR-021 para una READ, sí para efectos nuevos; inspección de entrega heredada de E2. |
| D8 Infraestructura | Monolito modular; imagen única, sin broker inicialmente | Ratificar recorte ADR-024 tras carga/shutdown; HTTP/worker solo por necesidad medida. |
| D9 Operación | RPO 24 h / RTO 1 h y latencia provisional de GOALS | Responsable ratifica SLO, retención, región/costo en E3-01. |
| D10 Evaluación | eval-e3 independiente, límites sin fijar | Registrar presupuesto antes de APIs reales; conservar contadores previos. |

## Dependencias revisadas

Diseño/fixtures E3 puede avanzar con Gates B/C E2 abiertos. Gate E3-0 completo requiere A/B/C; Neon sintético no implica migración autorizada de tráfico. E3-02 define identidad junto con datos antes de E3-03; pruebas de identidad usan fakes antes de knowledge. Gate E3-2 no depende de RAG construido; E3-4 revalida aislamiento en retrieval. Lead/case son registros internos en el primer corte; la integración CRM/helpdesk con mutations es incremento posterior.

## Riesgos y mitigación

| Riesgo | Mitigación verificable |
| --- | --- |
| Pérdida de autoridad al compartir pool | Contexto scoped por transacción, rol runtime limitado, test de conexión reutilizada. |
| Replay por lease vencido | Fencing/versión y cuarentena de efectos inciertos; no replay ciego. |
| Inconsistencia conversación/outbox | UoW compartido y fallos alrededor de cada commit. |
| Ingestión parcial o fuente revocada | Versiones activas y exclusión inmediata, swap atómico. |
| LLM propone acción fuera de scope | PEP determinista en cada acceso; prompts no amplían permisos. |
| Gates nominales sin evidencia | VERIFICACION enlaza ejecución/configuración/commit y mantiene pendientes visibles. |

Si una dependencia requiere un proveedor, credencial o decisión del responsable, terminar fixtures y contratos y registrar el bloqueo concreto en PROGRESS; no declarar completada la integración real.
