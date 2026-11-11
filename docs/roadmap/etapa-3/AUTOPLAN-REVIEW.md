# Revisión del plan — decisiones y gates

Fecha de revisión: 2026-10-15. Esta planificación no ratifica ADR globales abiertos. Una resolución local explicita alcance y evidencia antes de avanzar.

| Decisión | Propuesta / estado | Resolución necesaria |
| --- | --- | --- |
| D0 Baseline local | E3-D0-L usa Docker Compose, PostgreSQL local, migrador separado y una app única loopback con adapters deterministas. | Acreditado en Compose local; no cierra H1–H5 ni ratifica ADR-024. |
| D1 Persistencia | Neon/`psycopg`, migraciones, roles y restore acreditados en rama sintética | Registrar decisión E3-1; ratificar operación productiva y vigencia de evidencia. |
| D2 Estado canónico | ADR-008 Accepted: Conversation autoridad; runtime privado | UoW/IDs y recovery tienen slice SQLite/PostgreSQL; completar E3-0 y frontera GraphState. |
| D3 Identidad | Bindings de canal + membresías server-side | Elegir proveedor auth solo si se habilita HTTP; no construir auth casero; E3-0/2. |
| D4 Concurrencia | Claims/fencing y un consumidor por bot; workers condicionados a evidencia | Campaña H1 acredita reservas/fencing y recovery sintéticos; registrar decisión E3-1. |
| D5 Integración | Una fuente READ por Tool Layer | Open Food Facts v3 pasó smoke READ; completar campaña E3-3 y operación/presupuesto. |
| D6 RAG | ADR-010 Accepted: Neon/PostgreSQL + pgvector, una base por deployment. Slice offline usa dimensión 384 y `hash-384-v1-offline` sólo en pruebas. | Seleccionar y versionar modelo semántico real antes de indexar datos no sintéticos; acreditar exacta/HNSW, ingestión, revocación y operación en bases separadas. |
| D7 Efectos | Mutations externas apagadas; leads/cases internos autorizados | No exigir ADR-021 para una READ, sí para efectos nuevos; inspección de entrega heredada de E2. |
| D8 Infraestructura | **Resuelto 2026-10-23:** opción A (un contenedor) con ruta documentada a B (N réplicas); ADR-024 Aceptado | Disparadores de escala a B en ADR-024; la evidencia de carga/shutdown/rollback sigue pendiente en E3-5. Docker Compose no decide producción. |
| D9 Operación | **Resuelto 2026-10-23:** p95 ≤5 s, RPO ≤12 h (antes 24 h), RTO ≤1 h; retención/región sin cambios | Ratificado por el responsable; el cumplimiento se mide en la campaña E3-5. |
| D10 Evaluación | eval-e3 independiente; límites ratificados 2026-10-23 (`config/e3/limits.example.yaml`) y presupuesto Neon/OpenAI de la campaña integrada aprobado | Conservar contadores previos; reconciliar costo facturado en E3-5. |

## Baseline E3-D0 y frontera de autoridad

E3-D0 se denomina así para no confundirlo con E3-0. D0-L es una evidencia local acreditada de instancia única: el host expone sólo loopback, el ingress sin autenticación recibe mensaje y clave de conversación, y el scope sintético configurado sustituye cualquier identidad de payload. Cada turno HTTP recibe un `execution_id` nuevo, conserva el `conversation_id` y puede recorrer una capability distinta; el commit durable termina el turno antes de la siguiente solicitud.

No se desplega un contenedor por moneda, eje o círculo, ni existe un loop interno ilimitado. El flujo es `turno entrante → Contexto → eje de routing → capability/círculo → outcome → commit durable → siguiente turno`. D0-L no conecta LLM, Telegram, tools, Neon ni pgvector. D0-R queda diferido hasta H1–H4, credenciales y presupuesto aprobados; reutilizará imagen/contrato y tendrá evidencia separada de Neon, pgvector, READ, LLM, audit y métricas.

## Dependencias revisadas

Diseño/fixtures E3 puede avanzar con Gates B/C E2 abiertos. E3-D0-L puede ejecutarse en paralelo como baseline de packaging, sin convertir PostgreSQL local en evidencia H1. Gate E3-0 completo requiere A/B/C; Neon sintético no implica migración autorizada de tráfico. E3-02 define identidad junto con datos antes de E3-03; pruebas de identidad usan fakes antes de knowledge. Gate E3-2 no depende de RAG construido; E3-4 revalida aislamiento en retrieval. Lead/case son registros internos en el primer corte; la integración CRM/helpdesk con mutations es incremento posterior.

## Riesgos y mitigación

| Riesgo | Mitigación verificable |
| --- | --- |
| Pérdida de autoridad al compartir pool | Contexto scoped por transacción, rol runtime limitado, test de conexión reutilizada. |
| Replay por lease vencido | Fencing/versión y cuarentena de efectos inciertos; no replay ciego. |
| Inconsistencia conversación/outbox | UoW compartido y fallos alrededor de cada commit. |
| Ingestión parcial o fuente revocada | Versiones activas y exclusión inmediata, swap atómico. |
| LLM propone acción fuera de scope | PEP determinista en cada acceso; prompts no amplían permisos. |
| Gates nominales sin evidencia | VERIFICACION enlaza ejecución/configuración/commit y mantiene pendientes visibles. |
| Endpoint local sin autenticación expuesto fuera de su alcance | Publicar sólo en `127.0.0.1`, rechazar identidad/deployment del payload y prohibirlo en staging/producción. |
| Compose se interpreta como topología productiva | Declarar E3-D0 como instancia única local; ADR-024 quedó Aceptado el 2026-10-23 (opción A con ruta a B); réplicas y Kubernetes siguen fuera de esta etapa. |
| Loop de negocio convertido en proceso infinito o despliegues por dominio | Un request termina tras outcome/commit; encadenar por HTTP y mantener monedas/ejes/círculos dentro del monolito. |

Si una dependencia requiere un proveedor, credencial o decisión del responsable, terminar fixtures y contratos y registrar el bloqueo concreto en PROGRESS; no declarar completada la integración real.
