# Base — capacidades, contexto y frontera multicanal

Estado: contratos validados e implementados (H0 completado 2026-10-06); APIs activas en `modules/orchestration/domain/` y `foundation/config_e2.py`.

## Punto de partida comprobado

`Profile` solo tiene specialty, purpose, instructions y model; exige un saludo y una frase de hasta 30 palabras. `ConversationSession` guarda pares en memoria; `HandleMessage` crea nuevos request/execution IDs en cada invocación. El router de palabras clave se ejecuta dentro del adapter de LangGraph. `compose` fija scope local y el mismo modelo para los tres perfiles. No hay ledger de idempotencia, adapter Telegram ni persistencia conversacional.

## Recorrido objetivo

```text
Telegram inbound adapter / CLI / canal fake
  → entrada neutral + resolución confiable de scope
  → inbox: reservar evento y obtener ejecución estable
  → contexto conversacional mínimo + capabilities elegibles
  → DecisionModelPort → CapabilityResolver → RouteDecision
  → AgentDiscoveryPort → candidatos → Selection / Policy
  → ContextBuilder: contexto específico del especialista
  → WorkflowRuntimePort → LangGraph adapter → PEP → LLMPort
  → ExecutionOutcome propio
  → ResponseContextPort.contextualize → ContextualizedResponse
  → conversación + outcome + entrega pendiente (transacción local)
  → dispatcher → ChannelDeliveryPort → Telegram outbound adapter
```

Los nodos quedan como puentes delgados; routing, selección y construcción de contexto pertenecen a Application. Mantener los PEP junto a cada operación protegida, incluida clasificación externa, generación y entrega. Discovery y confidence no conceden autoridad. `REQUIRE_APPROVAL` bloquea la operación y da resultado seguro mientras no exista resume funcional.

## Ownership y contratos

| Dueño | Contrato propuesto | Responsabilidad |
| --- | --- | --- |
| Conversation/Application | `InboundMessage` | Versión, clave de evento externa normalizada, referencia opaca de canal/conversación/remitente, texto e instante. Sin Update/SDK. Scope se resuelve en servidor. |
| Identity/Tenant | Resolver de scope | Vincular cuenta/canal/remitente autorizados a deployment, tenant, actor y conversation del producto; rechazar desconocidos. |
| Orchestration | `DecisionModelPort`, `RouteDecision` | Clasificar sobre capabilities elegibles; devolver RESOLVED/AMBIGUOUS/UNSUPPORTED y señales; sin nombres de agents o modelos en decisión. |
| Orchestration | `AgentDiscoveryPort` | Query tipada → conjunto filtrado por capability, scope, estado y compatibilidad. Selection elige con regla explícita y estable. |
| Conversation + Orchestration | `ConversationRepositoryPort`, `ContextBuilder` | Estado canónico y selección de historia/hechos por necesidad del perfil. ContextBuilder es servicio de Application; no requiere un puerto artificial si no cruza una frontera. |
| Conversation/Application | `ResponseContextPort.contextualize(ResponseContextRequest)` | Construir la contextualización semántica que se entrega a cualquier gateway: respuesta pública, especialidad, idioma y continuidad visible permitida. Implementación inicial in-process. |
| Conversation | `ContextualizedResponse` | contract_version, response_id, request_id, execution_id, scope, destination_ref opaca, texto/bloques públicos tipados, specialty y reply_to opcional. |
| Conversation | `ChannelDeliveryPort.deliver(DeliveryRequest)` | Ejecutar entrega de una respuesta contextualizada ya persistida; resultado confirmado/fallido/incierto e identificador externo si existe. |
| Conversation | Inbox/outbox y repositorios | Reserva atómica, estados de procesamiento/entrega, hashes, correlación, recuperación y retención; adapters in-memory para pruebas y durable para piloto. |

`ResponseContextPort` es el puerto de construcción solicitado, compartido por todos los gateways. `ChannelDeliveryPort` separa el efecto de envío de esa construcción: Telegram implementa el adaptador de entrega y aporta el adaptador de entrada. No existe `TelegramPort` ni decisiones de canal en el especialista. El núcleo construye contenido público neutral; el adapter realiza formato, límites y mapping a la API específica.

El contexto de inferencia y el contexto público de respuesta son tipos distintos. No se envían al usuario las instrucciones internas, policy, historial completo ni paquetes de contexto. Un mapper explícito selecciona solo campos públicos; los tests con canarios comprueban que no se filtren.

## Compatibilidad

Conservar StartExecutionRequest/ExecutionOutcome del ADR-007 y su discriminación de variantes. Añadir contexto y selección mediante tipos propios versionados, con serialización de ida y vuelta y compatibilidad de CLI. request_id identifica la interacción; execution_id identifica la ejecución lógica; conversation_id persiste entre turnos. La clave de deduplicación tiene semántica aparte: reentregar el mismo evento recupera los IDs guardados, no llama de nuevo al generador de UUID.

Schema desconocido se rechaza de manera segura; campos requeridos no pasan como diccionarios libres. `GraphState`, checkpoints y runtime thread ID quedan privados. El envelope de ADR-023 puede orientar la evolución, pero sigue Proposed y no reemplaza ADR-007.

## Persistencia mínima propuesta

Scope = `ExecutionScope` existente (`foundation/contracts/execution.py`); no se crea un tipo nuevo. La CLI construye un `InboundMessage` con `channel="cli"`, `external_event_id="cli:<uuid4>"` y un binding fijo `local/local/local-user`; la conversación CLI se reinicia en cada proceso, como en etapa 1.

Tablas mínimas (SQLite, `sqlite3` de la stdlib, `journal_mode=WAL`, ruta `INCUBIA_DB_PATH`, por defecto `~/.local/state/incubia/e2.sqlite3`):

| Tabla | Clave única | Columnas clave |
| --- | --- | --- |
| `bindings` | `(channel, channel_account_ref, external_chat_ref, external_sender_ref)` | `binding_id`, campos de `ExecutionScope`, `enabled`. |
| `inbox_events` | `(deployment_id, tenant_id, channel_account_ref, external_event_id)` | `payload_hash` (sha256 del JSON canónico de `InboundMessage`), `request_id`, `execution_id`, `state`, `error_code`, `received_at`. |
| `conversations` | `conversation_id` | `revision` (entero), `active_capability`, `facts_json`. |
| `turns` | `(conversation_id, execution_id)` | `user_text`, `assistant_text`, `capability`, `profile_version`, `created_at`. |
| `outcomes` | `execution_id` | JSON de `ExecutionOutcome` con `to_dict`. |
| `deliveries` | `(execution_id, response_id, destination_ref)` | `payload_json`, `state`, `attempts`, `next_attempt_at`, `external_message_id`. |
| `runner_state` | `channel_account_ref` | `last_offset`. |

Esquema versionado con `PRAGMA user_version` y migraciones numeradas en `adapters/persistence/sqlite/migrations/`.

Retención por defecto: 30 días para `inbox_events`, `turns`, `outcomes` y `deliveries`. Purga con `incubia-bot purge --before <fecha>`. La ventana de replay de Telegram (24 h) queda cubierta. Un evento cuyo `update_id` sea ≤ `last_offset` y no esté en inbox se descarta como `STALE`. Un runner por bot; el procesamiento queda serializado por el loop síncrono (ver TELEGRAM § Runner). Guardar inbox, IDs, outcome terminal, revisión de contexto/perfil y outbox. Actualizar conversación, outcome y outbox en una transacción; no mantenerla abierta durante llamadas de red. Claves únicas y control de versión protegen duplicados y turnos concurrentes. Si el proceso cae durante inferencia o envío, recuperar un estado explícito de incertidumbre; no inferir que la ausencia de resultado autoriza repetir.

La retención del ledger debe cubrir como mínimo toda la ventana de replay admitida; eventos anteriores al corte de retención se rechazan o se revisan, nunca se tratan silenciosamente como nuevos. Definir duración, borrado y acceso en H0. Persistencia de piloto no acredita aislamiento productivo ni memoria de largo plazo.
