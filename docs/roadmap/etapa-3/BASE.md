# Base — arquitectura y contratos de etapa 3

Estado: diseño objetivo. Rutas relativas a `src/incubia_orchestrator/`. Preservar [spec 07](../../specs/07-evolucion-contextos.md) y ADR-001/005/006/007/008/010; las propuestas 009/019/021/023/024 requieren resolución del alcance aplicable.

## Recorrido

```text
CLI / Telegram / futura entrada HTTP
 → autenticación o binding confiable → Principal → ExecutionScope
 → inbox y IDs estables → contexto canónico → capability/discovery/selection
 → PEP → propuesta de tool / retrieval → policy → adapter autorizado
 → EvidenceItems acotados → ContextBuilder → LLMPort → outcome
 → contextualización pública → commit conversación + outcome + outbox → entrega
 → eventos de auditoría y métricas correlacionados
```

La semántica vive en Application. Los nodos LangGraph conectan servicios mediante contratos propios. El runtime no importa adapters concretos. El loop tiene deadline y máximo de pasos configurable; al agotarlos devuelve error seguro o caso, sin repetir efectos.

## Ownership

| Dueño | Contratos / rutas objetivo | Responsabilidad |
| --- | --- | --- |
| identity_tenant | `ports/identity.py`, `domain/principal.py`, `application/resolve_scope.py` | Autenticación delegada o binding administrado, membresía/rol, revocación y scope confiable. |
| conversation | Puertos existentes de repository + nuevo `ports/ledger.py` extraído del uso SQLite | Reserva/claims, lectura scoped, revisión, commit conjunto outcome/turn/outbox. |
| governance | PolicyEnginePort existente y `application/authorize_tool.py` | PEP/PDP determinista por operación, tenant, rol y recurso; incertidumbre bloquea. |
| orchestration | `ports/tool_discovery.py`, `ports/tool_executor.py`, `domain/tools.py` | Registry y discovery de herramientas; ejecución tipada mediante adapters; separar solicitud del agente de autorización. |
| knowledge | `ports/{retrieval,embedding,knowledge_repository}.py` | Ingestión, versiones, chunks, generaciones pgvector y resultados; su Data Plane se aísla por base de deployment. |
| audit | `ports/event_sink.py`, `domain/events.py` | Eventos sanitizados y correlación; no guardar prompts ni credenciales por defecto. |
| sales / support | Repositorios y casos de uso de lead/case | Registros internos, consentimiento, deduplicación y consulta autorizada. |
| bootstrap | `composition.py` + composición E3 | Instanciar adapters, credenciales, límites y configuración; mantener modo offline. |

No crear todas las carpetas anticipadamente. Abrir cada módulo con su primer slice y dueño de datos. ConversationMemoryPort solo se añade si existe una frontera distinta del repositorio/context builder; evitar puertos duplicados.

## Contratos propuestos

`ToolInvocationRequest`: contract_version, tool_call_id, request_id, execution_id, scope, tool_id/version, input específico, deadline y budget_ref. `ToolExecutionResult`: status COMPLETED/DENIED/FAILED/UNKNOWN_EFFECT, output tipado o error de producto, evidence_ref y metadata sanitizada. Schema desconocido y campos inesperados fallan antes del adapter. Limitar tamaño de input/output.

`RetrievalRequest`: scope confiable, query, source_ids autorizados, top_k ≤5, deadline y presupuesto. La resolución del `deployment_id` escoge la base/cuenta de Knowledge antes de invocar el adapter. `EvidenceItem`: source_id/version, chunk, generación, localizador público permitido, contenido, instante y score opcional. Score no concede autoridad. No copiar secretos/ACL completos al prompt; los documentos son datos no confiables.

## Persistencia y concurrencia

Neon detrás de un driver PostgreSQL estándar. El slice E3-03 usa `psycopg` y migraciones SQL versionadas; no introducir ORM como dependencia de Domain. La base de Control Plane contiene bindings/memberships, inbox_events, conversations, turns, outcomes, deliveries, claims, tool_calls, audit_events, leads y cases. Cada base de Knowledge por deployment contiene fuentes, chunks, embeddings y generaciones pgvector. Cada módulo conserva ownership aunque comparta una base.

Un Unit of Work de Conversation ofrece commit atómico de turno/revisión/outcome/inbox/outbox. Adaptar SQLite y PostgreSQL al mismo contrato sin reescribir los adapters de canal. Claves únicas incluyen deployment/tenant y la identidad del evento acordada en E3-02; misma clave con hash distinto produce conflicto.

Claims PostgreSQL usan compare-and-set, vencimiento y fencing token; un dueño vencido no puede hacer commit. Serializar por conversación mediante reserva/versión compartida. No trasladar el file lock SQLite como solución multi-host. Un consumidor activo por cuenta Telegram con elección de dueño; múltiples workers internos solo después de demostrar reserva exclusiva. Outbox SENDING incierto permanece UNKNOWN_EFFECT; vencer lease no autoriza repetir envío.

Para Control Plane y Conversation, RLS es defensa adicional con rol runtime sin bypass, contexto de tenant establecido dentro de transacción y limpieza al devolver conexión al pool. Pruebas alternan tenants sobre la misma conexión. En Knowledge, la defensa de frontera entre clientes es la base y el pool por deployment; ACL/RLS interno sólo gobierna documento, rol o departamento cuando aplique. Migrador usa otro rol; consultas operativas cross-tenant o cross-deployment son explícitas y auditadas.

Checkpoints solo se habilitan si hay resume real con contratos ADR-007; no asumir atomicidad con otra base. El primer corte puede dejar PROCESSING incierto en NEEDS_INSPECTION según E2. Lead/case internos tienen clave lógica única; exports externos requieren Tool Layer y autorización de mutations.
