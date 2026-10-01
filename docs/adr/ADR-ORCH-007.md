<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-007-execution-contract-independiente-del-runtime-75eb46c3d112
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-007 — Execution Contract independiente del runtime

**Status:** Accepted
**Scope:** `incubia-ai-orchestrator`

## Context

El Orchestrator necesita intercambiar solicitudes, reanudaciones y outcomes entre Application y el runtime sin utilizar objetos propios de LangGraph, OpenAI u otros frameworks como contratos internos.

Tras cerrar `ADR-ORCH-001`, la frontera queda definida de la siguiente manera:

* el producto es dueño de la semántica de la ejecución;
* LangGraph es dueño de la mecánica de ejecución;
* `Domain` y `Application` no conocen `GraphState`, `thread_id`, checkpoints, `Command`, interrupts ni errores específicos del runtime.

El contrato debe expresar necesidades del producto y no replicar la API de LangGraph.

## Decision

Se adopta una familia de contratos de ejecución propia del producto, framework-neutral, tipada y serializable.

El lifecycle mínimo será:

```text
StartExecutionRequest
ResumeExecutionRequest
ExecutionOutcome
```

`ExecutionOutcome` será una unión discriminada de:

```text
CompletedExecution
SuspendedExecution
FailedExecution
```

El runtime será consumido mediante:

```text
WorkflowRuntimePort
├── start(StartExecutionRequest) -> ExecutionOutcome
└── resume(ResumeExecutionRequest) -> ExecutionOutcome
```

No se expondrán primitivas específicas como `invoke`, `ainvoke`, `Command`, `thread_id`, checkpoints o interrupts en el puerto del producto.

## Lifecycle

```text
StartExecutionRequest
        │
        ▼
WorkflowRuntimePort.start()
        │
        ▼
      Runtime
        │
   ┌────┼──────────────┐
   ▼    ▼              ▼
Completed Suspended   Failed
             │
             │ posteriormente
             ▼
ResumeExecutionRequest
             │
             ▼
WorkflowRuntimePort.resume()
```

Una ejecución suspendida y posteriormente reanudada conserva el mismo `execution_id`.

## Identificadores

Se distinguen explícitamente los siguientes identificadores:

### `conversation_id`

Identifica la conversación lógica del producto y puede contener múltiples ejecuciones.

### `execution_id`

Identifica una ejecución lógica del Orchestrator. Permanece estable durante suspensión y reanudación.

### `request_id`

Identifica una invocación/interacción concreta con el Orchestrator y facilita tracing, auditoría y correlación.

Ejemplo:

```text
request-001
   ↓
start execution-837
   ↓
SUSPENDED

request-002
   ↓
resume execution-837
   ↓
COMPLETED
```

### Identificadores del runtime

Identificadores como `runtime_thread_id`, `thread_id`, `checkpoint_id` u otros equivalentes no formarán parte del Execution Contract público.

El adapter podrá mantener mappings internos como:

```text
execution_id
    ↕
runtime_thread_id
```

## Execution Scope

El contrato deberá transportar el alcance necesario para resolver contexto y políticas sin asumir que Incubia es siempre el operador.

Conceptualmente:

```text
ExecutionScope
├── deployment_id
├── tenant_id
├── conversation_id
└── actor_id
```

`deployment_id` forma parte del contrato desde el MVP para preservar la distinción entre deployment/operator y tenant establecida en `ADR-ORCH-001`.

El scope transporta identidad y alcance, no toda la configuración efectiva.

## Policies

No se incluirán completas dentro de `StartExecutionRequest` estructuras como:

```text
ProductPolicy
OperatorPolicy
TenantPolicy
Permissions snapshot
```

Estas deberán resolverse mediante sus puertos/capacidades correspondientes cuando sean necesarias.

El Execution Contract transportará información suficiente para resolverlas, no copias arbitrarias de configuración.

## Execution Input

El runtime no recibirá objetos propios de canales externos como:

```text
FastAPI Request
WhatsApp payload
Telegram Update
Twilio object
```

La entrada será normalizada mediante un contrato propio del producto.

Para el MVP:

```text
ExecutionInput
├── content_type
├── content
├── locale? 
└── channel?
```

Inicialmente `TEXT` será suficiente como tipo principal, dejando otros tipos para evolución posterior.

## StartExecutionRequest

Conceptualmente:

```text
StartExecutionRequest
├── request_id
├── execution_id
├── scope
└── input
```

No se incluyen obligatoriamente:

* intent;
* capability;
* agent;
* tools;
* retrieval context;
* GraphState;
* checkpoint;
* model.

Estos conceptos pueden no existir todavía al comenzar la ejecución y algunos serán definidos por otros ADRs.

## Routing information

`intent` y `capability` no serán campos obligatorios del Start Contract.

Podrán existir en el futuro hints opcionales si un caller ya conoce una ruta, pero el modelo definitivo dependerá de `ADR-ORCH-003`.

## ExecutionOutcome

Se adopta `ExecutionOutcome` en lugar del nombre simple `ExecutionResult`, ya que una ejecución puede terminar, suspenderse o fallar.

### CompletedExecution

Representa una ejecución completada correctamente desde la perspectiva del sistema.

Conceptualmente:

```text
CompletedExecution
├── request_id
├── execution_id
├── status = completed
└── output
```

### SuspendedExecution

Representa una ejecución válida que requiere continuación posterior.

Conceptualmente:

```text
SuspendedExecution
├── request_id
├── execution_id
├── status = suspended
└── suspension
```

La suspensión expondrá un identificador propio del producto, por ejemplo:

```text
continuation_id
```

El mapping entre `continuation_id` y primitivas internas de LangGraph pertenece exclusivamente al runtime adapter.

La forma detallada de `SuspensionDescriptor` y Human-in-the-Loop se definirá en `ADR-ORCH-012`.

### FailedExecution

Representa fallos reales de ejecución o infraestructura.

Conceptualmente:

```text
FailedExecution
├── request_id
├── execution_id
├── status = failed
└── error
```

Los errores específicos del runtime deberán mapearse a errores propios del producto, por ejemplo:

```text
GraphRecursionError
      ↓ mapper
ExecutionLimitReached
```

El contrato no propagará excepciones específicas de LangGraph, OpenAI u otros proveedores.

## Business outcomes vs failures

Una decisión esperada de negocio o policy no implica necesariamente un fallo técnico.

Ejemplo:

```text
Policy = DENY
```

puede producir una ejecución correctamente completada con una respuesta indicando falta de autorización.

Por tanto:

```text
expected business outcome ≠ system failure
```

Esta separación deberá preservarse en observabilidad y auditoría.

## Handoff y flags

No se adoptarán flags genéricos como:

```text
handoff_required
needs_approval
needs_user
retry_required
```

El contrato evolucionará mediante outcomes y descriptors tipados cuando dichos conceptos sean definidos en sus ADRs correspondientes.

## Metadata

Se evitará utilizar `metadata: dict[str, Any]` como mecanismo general de expansión del contrato.

Los conceptos arquitectónicamente relevantes deberán modelarse mediante tipos explícitos, por ejemplo:

```text
ExecutionScope
ExecutionInput
ExecutionOutput
TraceContext
SuspensionDescriptor
ExecutionError
```

## Serialización y neutralidad de framework

Todos los contratos de ejecución deberán ser serializables y no contener objetos de infraestructura o framework.

Esto permitirá que durante el MVP viajen en memoria y que posteriormente puedan transportarse mediante HTTP, queues, workers o mecanismos distribuidos sin cambiar su modelo conceptual.

Quedan explícitamente prohibidos dentro del contrato:

```text
DB sessions
OpenAI clients
compiled graphs
GraphState
checkpoints
framework requests
SDK response objects
```

## Implementación inicial

Para los contratos internos se priorizan tipos simples y framework-neutral, por ejemplo:

```text
dataclass(frozen=True)
Enum
Value Objects
```

El uso de Pydantic podrá existir en adapters como HTTP para validación de entrada/salida, pero no será una dependencia obligatoria del contrato arquitectónico interno.

## Streaming

Streaming queda fuera de la primera versión de este ADR.

Si el producto requiere streaming posteriormente, se modelará mediante eventos propios del producto, por ejemplo:

```text
ExecutionStarted
OutputDelta
ExecutionSuspended
ExecutionCompleted
ExecutionFailed
```

No se expondrán directamente eventos internos de LangGraph.

## Regla de evolución

Antes de agregar un campo al Execution Contract deberá responderse:

> ¿Este concepto existe porque el producto lo necesita o porque el runtime tiene una propiedad equivalente?

Si existe únicamente por LangGraph u otro framework, deberá permanecer dentro del adapter/mapping correspondiente.

## Campos permitidos y no permitidos

### Permitidos conceptualmente

* `request_id`;
* `execution_id`;
* `conversation_id`;
* `deployment_id`;
* `tenant_id`;
* `actor_id`;
* normalized input;
* execution outcome;
* continuation ID;
* safe execution error.

### No permitidos

* `thread_id`;
* `checkpoint_id`;
* `GraphState`;
* node name como dependencia del consumidor;
* edge;
* `Command`;
* LangGraph interrupt ID;
* OpenAI response objects;
* DB sessions;
* raw tenant configuration;
* objetos específicos de SDKs/frameworks.

## Consequences

### Positive

* Los casos de uso no conocen tipos del runtime.
* El lifecycle start/suspend/resume queda representado explícitamente.
* Facilita contract tests entre runtimes.
* Permite reemplazar LangGraph sin modificar consumidores centrales.
* Evita convertir `ExecutionRequest` en una copia de `GraphState`.
* La distinción `request_id` / `execution_id` / `conversation_id` mejora tracing y auditoría.
* La inclusión de `deployment_id` soporta customer-managed, private cloud y otros modelos de operación.
* Los contratos quedan preparados para transporte distribuido futuro sin obligar a distribuir el MVP.

### Negative / Cost

* Requiere mapping entre contratos del producto y tipos concretos del runtime.
* Introduce varios tipos en lugar de un único request/result genérico.
* La suspensión requiere gestionar `continuation_id` y mappings internos.
* La evolución del contrato debe ser deliberada y coordinada con otros ADRs.

## Alternatives considered

### `ExecutionRequest -> ExecutionResult` único

No adoptado porque no representa correctamente suspensión y reanudación.

### Utilizar directamente `GraphState`

Rechazado porque acoplaría Application a LangGraph.

### Diccionarios sin contrato explícito

Rechazado porque reduce type-safety, trazabilidad y evolución controlada.

### Copiar toda la API de LangGraph detrás de un puerto propio

Rechazado porque crearía una abstracción artificial del framework y dañaría la reemplazabilidad real.

### `metadata: dict[str, Any]` extensible

No adoptado como estrategia principal porque debilita el contrato y oculta conceptos relevantes.

## Validation criteria

La decisión se considera correctamente implementada cuando:

* existe `WorkflowRuntimePort.start()`;
* existe `WorkflowRuntimePort.resume()`;
* ambos utilizan contratos propios del producto;
* existe distinción entre `conversation_id`, `execution_id` y `request_id`;
* `deployment_id` y `tenant_id` forman parte del scope de ejecución;
* `ExecutionOutcome` representa completed, suspended y failed;
* una ejecución suspendida puede reanudarse sin exponer `thread_id` ni `Command` a Application;
* los errores de runtime son mapeados a errores propios del producto;
* los contratos pueden serializarse sin objetos de framework;
* los tipos de LangGraph permanecen dentro del adapter correspondiente;
* no se utiliza `GraphState` como contrato interno del producto.

## Deferred decisions

Se delegan deliberadamente a ADRs específicos:

* `ADR-ORCH-003` — intent/capability routing;
* `ADR-ORCH-006` — PolicyContext y resolución de políticas;
* `ADR-ORCH-011` — handoffs;
* `ADR-ORCH-012` — suspensión y Human-in-the-Loop detallado;
* `ADR-ORCH-014` — tracing, audit y execution events.

## Related

* `ADR-ORCH-001` — LangGraph como runtime reemplazable de orquestación;
* `ADR-ORCH-019` — Separación entre Conversation State y GraphState;
* SAD v1.1 — Incubia AI Orchestrator;
* Draft — Estructura del repositorio `incubia-ai-orchestrator`.

