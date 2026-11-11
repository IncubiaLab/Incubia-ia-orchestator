# ADR-ORCH-008 — Persistencia de Conversation State

**Status:** Accepted — 2026-10-07  
**Fecha:** 2026-10-07  
**Scope:** `incubia-ai-orchestrator`, Conversation y sus adapters de persistencia  
**Fuente de seguimiento:** [HEC-33](https://linear.app/hector-cruz/issue/HEC-33/adr-orch-008-persistencia-de-conversation-state) · [documento en Linear](https://linear.app/hector-cruz/document/adr-orch-008-persistencia-de-conversation-state-fdd6d6e45d7b)

## Contexto

El ledger SQLite de etapa 2 acredita una única ejecución y entrega lógica por
evento dentro de un host. Su tabla de conversaciones no termina aún el turno
con la clave de conversación ni mantiene su revisión canónica. En etapa 3 el
estado debe sobrevivir a procesos reemplazables, conservar la idempotencia de
etapa 2 y permitir aislamiento multi-tenant. El estado de LangGraph no puede
ocupar esta función: ADR-ORCH-019 lo mantiene privado del adapter runtime.

No existe una transacción compartida entre PostgreSQL y Telegram, un LLM u
otra integración. Por ello la decisión se centra en atomicidad local y en
representar explícitamente los efectos inciertos, no en prometer exactly-once
físico.

## Decisión

1. **Conversation es la autoridad canónica.** Conserva los turnos, hechos
   versionados, revisión y resultados lógicos que sean necesarios para retomar
   una interacción. `GraphState`, checkpoints y cualquier ID de runtime son
   privados de `modules/orchestration/adapters/runtime/` y no se persisten como
   estado de conversación.
2. Durante E3, una conversación se identifica de forma inequívoca por
   `(deployment_id, tenant_id, conversation_id, actor_id)`. Incluir el actor
   preserva el aislamiento del ledger E2 y evita que dos participantes de un
   mismo canal compartan historia por accidente. Una conversación compartida o
   con participantes explícitos requerirá un ADR posterior y una migración;
   no se infiere de un `conversation_id` suministrado por el cliente.
3. La entrada de canal se acepta con una clave inmutable
   `(deployment_id, tenant_id, channel, channel_account_ref,
   external_event_id)` y `payload_hash`. La misma clave y el mismo hash
   devuelve los IDs/estado ya reservados; la misma clave con otro hash produce
   `IdempotencyConflict` y no inicia otro procesamiento.
4. `request_id` y `execution_id` se asignan únicamente al aceptar una entrada
   nueva y se conservan en todos los replays. `response_id` identifica la
   respuesta lógica y `delivery` identifica su destino. Ningún runtime, nodo o
   reintento crea IDs alternativos para la misma entrada.
5. `ConversationUnitOfWork` será el único mecanismo para el commit final de
   Conversation. Dentro de una transacción corta debe comprobar scope,
   `expected_revision` y claim/fencing vigente, añadir el turno, incrementar
   la revisión, guardar outcome y crear outbox/delivery, y terminar el inbox.
   Todo confirma o revierte junto. Los repositorios participantes no hacen
   commits ocultos dentro de esa unidad.
6. La ejecución de LLM, retrieval, tool y entrega de canal sucede fuera de
   esa transacción. Tras una llamada externa se vuelve a validar autoridad,
   revisión, claim y deadline antes del commit. Un conflicto no autoriza
   repetir automáticamente una llamada externa.
7. `PROCESSING` cuyo dueño deja de ser válido pasa a
   `NEEDS_INSPECTION` mediante recuperación explícita. Un delivery en
   `SENDING` cuyo resultado no se puede demostrar pasa a `UNKNOWN_EFFECT` y
   no se reenvía automáticamente. `SENT` nunca vuelve a `PENDING`.
8. SQLite sigue siendo un adapter local/offline con este contrato. PostgreSQL
   (Neon para Tier 3, según ADR-ORCH-025) debe ofrecer el mismo comportamiento
   observable; las diferencias de SQL, pool y RLS permanecen en adapters.

## Modelo y fronteras de datos

Conversation es dueño de `inbox_events`, `conversations`, `turns`, `outcomes`,
`deliveries` y `claims`. Identity/Tenant es dueño de `bindings` y
`memberships`; Conversation los consulta mediante un puerto scoped y no acepta
que un payload de canal establezca tenant o actor.

Las filas que relacionen una conversación, turno u outbox incluyen el scope
completo o una clave foránea compuesta que lo preserve. `execution_id` global
no sustituye los predicados de tenant/deployment. La revisión de conversación
es monotónica y se usa como compare-and-set; el token de fencing protege al
dueño de un claim frente a un dueño ya vencido.

El contrato E3-02 debe exponer, como mínimo, valores tipados para reserva de
inbox, snapshot de conversación, conflicto de revisión, conflicto de
idempotencia, claim y unidad de trabajo. Domain/Application no importan SQL,
tipos del driver, objetos de conexión ni LangGraph.

## Retención, recuperación y migración

Hasta que D9 ratifique una política para datos reales, las pruebas sintéticas
mantienen el comportamiento E2: siete días para payloads y treinta para
tombstones. La purga elimina primero los cuerpos retenidos y conserva las
claves de deduplicación durante el periodo de tombstone. Una política distinta
requiere responsable, fundamento de privacidad y actualización del runbook.

La migración SQLite → PostgreSQL conserva IDs, hashes de payload, revisiones y
claves de deduplicación. Usa export con manifest/hash y una importación
idempotente; ante un hash conflictivo se aborta. No habrá dual-write con
pretensión de atomicidad distribuida. El corte de autoridad, reconciliación y
restore se acreditan en E3-05 antes de cualquier dato real.

## Consecuencias

**Beneficios:** una fuente de verdad independiente del runtime; contrato
compartido SQLite/PostgreSQL; commits locales auditables; y recuperación
conservadora ante efectos remotos inciertos.

**Costes:** se introduce UoW, control de revisión y migración explícita; por
ahora cada actor tiene conversación independiente; y la recuperación puede
requerir inspección humana en vez de replay automático.

## Alternativas descartadas

### Usar GraphState/checkpoints como conversación durable

Se descarta porque acopla el modelo de producto a LangGraph y no expresa las
restricciones de inbox, outbox, scopes o delivery.

### Identificar la conversación solo por `conversation_id`

Se descarta porque no prueba aislamiento entre deployment, tenant ni actor y
abre la puerta a colisiones o acceso cruzado.

### Reprocesar automáticamente todo trabajo con lease vencido

Se descarta: una llamada de red podría ya haber producido un efecto. La
incertidumbre se representa y reconcilia antes de volver a intentar.

## Criterios de validación

- Las suites de contrato SQLite/PostgreSQL obtienen el mismo resultado para
  replay, payload conflictivo, revisión obsoleta y rollback de commit.
- Dos workers no pueden completar una misma conversación con el mismo o un
  fencing token vencido.
- Un fallo de transacción no deja turn/outcome/outbox/inbox parcialmente
  confirmados.
- Ningún módulo Conversation importa LangGraph ni SQL/driver fuera de sus
  adapters; `GraphState` sigue limitado al adapter runtime.
- E3-05 demuestra export/import/restore sintético y conserva IDs y dedup.

## Relacionado

- ADR-E2-001 — Ledger durable y recuperación para Gate A
- ADR-ORCH-007 — Execution Contract independiente del runtime
- ADR-ORCH-019 — Separación entre Conversation State y GraphState
- ADR-ORCH-025 — PostgreSQL administrado con Neon para Tier 3
- E3-02, E3-03, E3-04 y E3-05
