# Base — capacidades, contexto y frontera multicanal

Estado: contratos propuestos para H0; nombres orientativos, no APIs ya implementadas.

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

SQLite detrás de repositorios, un runner por bot y serialización de procesamiento por conversación. Guardar inbox, IDs, outcome terminal, revisión de contexto/perfil y outbox. Actualizar conversación, outcome y outbox en una transacción; no mantenerla abierta durante llamadas de red. Claves únicas y control de versión protegen duplicados y turnos concurrentes. Si el proceso cae durante inferencia o envío, recuperar un estado explícito de incertidumbre; no inferir que la ausencia de resultado autoriza repetir.

La retención del ledger debe cubrir como mínimo toda la ventana de replay admitida; eventos anteriores al corte de retención se rechazan o se revisan, nunca se tratan silenciosamente como nuevos. Definir duración, borrado y acceso en H0. Persistencia de piloto no acredita aislamiento productivo ni memoria de largo plazo.
