<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-001-langgraph-como-runtime-reemplazable-de-orquestacion-7991e40eb0c2
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-001 — LangGraph como runtime reemplazable de orquestación

**Status:** Accepted
**Scope:** `incubia-ai-orchestrator`

## Context

El Orchestrator necesita ejecutar workflows stateful con branches, loops, retries, pausas, reanudaciones y futuros handoffs. El SAD selecciona LangGraph para el MVP, pero también establece que la arquitectura no debe depender conceptualmente de LangGraph.

El riesgo a evitar es que `StateGraph`, `GraphState`, nodos o APIs concretas de LangGraph se propaguen hacia Application o Domain y conviertan el framework en la arquitectura del producto.

Adicionalmente, el MVP se diseña como un producto adaptable a múltiples clientes y posibles modelos de operación. No debe asumirse que Incubia será siempre el operador final de una instancia ni la autoridad sobre todas las reglas empresariales de un deployment.

Por ello, la frontera arquitectónica no debe formularse como “LangGraph vs reglas de Incubia”, sino como “runtime genérico vs políticas, configuración e invariantes del producto, deployment y tenant”.

## Decision

LangGraph se utilizará como runtime de ejecución stateful del MVP detrás de un puerto propio del producto.

Ubicación prevista:

```text
modules/orchestration/adapters/runtime/langgraph/
```

La capa Application dependerá de `WorkflowRuntimePort`, no de LangGraph.

```text
Application
    ↓
WorkflowRuntimePort
    ↑
LangGraphRuntimeAdapter
```

El dominio y los casos de uso no podrán importar directamente `langgraph` ni tipos concretos del framework.

LangGraph podrá encargarse de la mecánica de ejecución del workflow, incluyendo:

* graph traversal;
* runtime state;
* branches y conditional edges;
* loops;
* retries de ejecución;
* checkpointing;
* pause / resume;
* interrupts;
* streaming;
* manejo técnico de errores del runtime.

Estas capacidades deberán permanecer confinadas al adapter/runtime y no convertirse en modelos de dominio del producto.

## Neutralidad respecto al operador

El Orchestrator no asumirá que Incubia es siempre el operador, propietario de las reglas empresariales o autoridad final de una instalación.

El runtime deberá ser neutral respecto a quién opera el producto.

Se adopta la siguiente separación conceptual:

```text
Product / Kernel Invariants
        ↓
Deployment / Operator Policy
        ↓
Tenant / Business Policy
        ↓
Execution Context
        ↓
Workflow Runtime
        ↓
LangGraph
```

### 1. Product / Kernel Invariants

Restricciones no reemplazables necesarias para preservar seguridad, aislamiento y consistencia arquitectónica del producto.

Ejemplos:

* aislamiento entre tenants;
* autorización obligatoria para operaciones sensibles;
* prohibición de bypass del Policy Layer;
* trazabilidad mínima de ejecuciones;
* Domain y Application independientes del runtime;
* enforcement de límites estructurales del sistema.

Estas reglas no deben ser configurables por un tenant.

### 2. Deployment / Operator Policy

Políticas definidas por quien administra una instalación concreta del producto.

El operador puede ser Incubia, un cliente o un tercero autorizado.

Ejemplos:

* proveedores de LLM permitidos;
* uso exclusivo de modelos locales;
* límites máximos de ejecución;
* políticas de retención;
* restricciones de acceso a APIs externas;
* requisitos de aprobación humana.

### 3. Tenant / Business Policy

Reglas propias de cada organización que utiliza el producto.

Ejemplos:

* capacidades habilitadas;
* tools permitidas;
* reglas comerciales;
* límites operativos;
* flujos de escalamiento;
* permisos por rol;
* fuentes de conocimiento;
* agentes disponibles.

Estas reglas deben poder variar sin modificar el core del Orchestrator.

### 4. Execution Context

Información dinámica específica de una solicitud o ejecución.

Ejemplos:

* tenant;
* usuario;
* roles;
* permisos efectivos;
* canal;
* intent;
* capacidades disponibles;
* contexto recuperado;
* restricciones temporales de ejecución.

## Jerarquía de autoridad

Ante conflicto, se adopta conceptualmente la siguiente precedencia:

```text
Product / Kernel Invariants
        >
Deployment / Operator Policy
        >
Tenant / Business Policy
        >
Agent Decision
        >
LLM Suggestion
```

El detalle de cómo se representan, evalúan y combinan estas políticas será definido en `ADR-ORCH-006 — Policy Engine & Guardrails`.

## Terminología adoptada

Se evita utilizar nombres que presupongan que Incubia es siempre la autoridad operativa de una instalación.

Evitar:

```text
IncubiaRules
IncubiaPolicy
IncubiaPermissions
```

Preferir:

```text
ProductPolicy
KernelInvariant
OperatorPolicy
DeploymentPolicy
TenantPolicy
ExecutionPolicy
PolicyContext
```

Una posible estructura conceptual es:

```text
PolicyContext
├── ProductConstraints
├── DeploymentPolicy
├── TenantPolicy
└── ExecutionConstraints
```

## Responsabilidades del runtime

LangGraph ejecutará un workflow resuelto a partir de contratos y decisiones externas al runtime.

Conceptualmente:

```text
Request
   ↓
Context Resolution
   ↓
Policy Resolution
   ↓
Capability Resolution
   ↓
Orchestration Plan / Execution Request
   ↓
WorkflowRuntimePort
   ↓
LangGraphRuntimeAdapter
   ↓
LangGraph
```

LangGraph no será responsable de definir qué políticas empresariales existen ni quién tiene autoridad para configurarlas.

## Reemplazabilidad

La reemplazabilidad se garantiza hasta la frontera `WorkflowRuntimePort`.

Esto significa que otro runtime podrá implementarse sin modificar Domain ni los casos de uso centrales de Application, siempre que cumpla los contratos establecidos por el producto.

No se garantiza portabilidad automática de:

* checkpoints;
* GraphState;
* primitivas de interrupt/resume;
* historial interno del runtime;
* tipos de error específicos;
* otras estructuras internas de LangGraph.

La sustitución del runtime puede requerir un nuevo adapter y nuevos mappings.

## Frontera definitiva de responsabilidad: semántica vs mecánica

Se adopta como principio central:

> **El producto es dueño de la semántica de la ejecución; LangGraph es dueño de la mecánica de la ejecución.**

### Product Decision Layer

Responsable de determinar el significado y las restricciones de una ejecución:

* identidad, tenant y contexto efectivo;
* Product / Kernel Invariants;
* Deployment / Operator Policy;
* Tenant / Business Policy;
* intent y capability resolution;
* definición de agentes y tools disponibles;
* autorización de tools;
* reglas de negocio;
* selección de contexto;
* definición de éxito, fallo y escalamiento;
* decisión de requerir intervención humana;
* semántica de auditoría y eventos del producto.

### LangGraph Execution Layer

Responsable de la mecánica necesaria para ejecutar el workflow:

* graph traversal;
* node execution;
* edges y conditional edges;
* loops;
* runtime state propagation;
* checkpoints;
* interrupt / resume;
* technical retries;
* runtime timeouts;
* streaming;
* subgraphs;
* concurrencia interna del graph;
* lifecycle técnico de la ejecución.

LangGraph podrá ejecutar decisiones del producto, pero no definir su significado empresarial ni la autoridad que las origina.

## Reglas de frontera

### Human-in-the-Loop

La decisión de que una acción requiere aprobación humana pertenece a Product/Application/Policy. El mecanismo técnico de pausa y reanudación pertenece al runtime.

```text
Policy Decision
      │
      ├── ALLOW ──────────────► continuar
      ├── DENY ───────────────► resultado controlado
      └── APPROVAL_REQUIRED ──► LangGraph interrupt / resume
```

### Retries

Se diferencia entre:

* **technical retry:** timeout, fallo transitorio de red, error técnico recuperable → Runtime;
* **semantic/business fallback:** cambiar fuente, pedir aclaración, escalar, terminar o seleccionar otra estrategia → Product/Application.

### Tools

LangGraph puede coordinar el flujo de ejecución de una tool, pero la definición, disponibilidad, autorización y restricciones de una tool pertenecen al producto y al Policy Layer.

```text
Agent / LLM suggestion
        ↓
ToolRequest
        ↓
Tool Registry
        ↓
Policy Evaluation
        ↓
ToolExecutorPort
        ↓
Adapter
```

### Nodes

Los nodos de LangGraph deberán ser delgados y actuar principalmente como bridges de ejecución.

```text
LangGraph Node
      ↓
Application Use Case / Service
      ↓
Domain / Ports
```

No deberán contener reglas de autorización, reglas empresariales específicas del tenant ni lógica de dominio que pueda existir independientemente del runtime.

### Definición del graph

Para el MVP, la topología técnica del graph pertenecerá al `LangGraphRuntimeAdapter`.

No se introducirá un DSL o `WorkflowDefinition` genérico que replique abstracciones como `add_node`, `add_edge` o `conditional_edge` únicamente para ocultar LangGraph.

Application podrá seleccionar un workflow o execution profile mediante contratos propios del producto; el adapter será responsable de mapear dicha selección a graphs/subgraphs concretos.

La configuración de tenants deberá habilitar capacidades, políticas, agentes, tools o fuentes de conocimiento, no definir directamente `StateGraph`, nodes o edges.

## Estado y persistencia

Se adopta una separación explícita entre estado de producto y estado del runtime.

### Estado canónico del producto

Incluye, entre otros:

* Conversation;
* Tenant;
* User;
* Policies;
* business data;
* long-term memory;
* audit events.

### Estado del runtime

Incluye:

* GraphState;
* checkpoints;
* pending writes;
* runtime execution state;
* primitivas internas de pause/resume.

Los checkpoints de LangGraph no constituyen el repositorio canónico de Conversation ni de entidades de dominio.

Se adopta además la distinción conceptual entre:

```text
conversation_id   → identidad de una conversación del producto
execution_id      → identidad de una ejecución concreta del producto
runtime_thread_id → identificador interno del runtime / LangGraph
```

Ninguno de estos identificadores deberá considerarse equivalente por definición.

## Observabilidad y auditoría

La semántica de auditoría pertenece al producto y deberá mantenerse independiente de LangGraph.

Eventos conceptuales como:

* ExecutionStarted;
* PolicyEvaluated;
* CapabilitySelected;
* ToolRequested;
* ToolAuthorized;
* ToolExecuted;
* HandoffRequested;
* ExecutionCompleted;

deben poder existir aunque se sustituya el runtime.

LangGraph podrá aportar información técnica adicional como graph, node, checkpoint, runtime latency o runtime error.

## Matriz de ownership

| Responsabilidad | Owner |
| -- | -- |
| Product / Kernel Invariants | Product Core |
| Operator / Deployment Policies | Policy Layer |
| Tenant / Business Policies | Policy Layer |
| Authorization | Policy Layer |
| Tenant isolation | Product Core / Policy |
| Intent resolution | Application |
| Capability resolution | Application |
| Agent definitions | Product |
| Tool definitions | Product |
| Tool authorization | Policy Layer |
| Business rules | Domain / Application |
| Context selection | Application |
| Conversation | Conversation bounded context |
| Long-term memory | Memory / Knowledge |
| Workflow selection | Application |
| Graph topology | LangGraph Adapter |
| Graph state | LangGraph Runtime |
| Node execution | LangGraph Runtime |
| Branch / loop mechanism | LangGraph Runtime |
| Technical retries | LangGraph Runtime |
| Checkpoints | LangGraph Runtime |
| Interrupt / resume mechanism | LangGraph Runtime |
| Human approval decision | Policy / Application |
| Runtime streaming | LangGraph Runtime |
| Runtime errors | LangGraph → mapped by Adapter |
| Business failure semantics | Application |
| Audit semantics | Product |
| Runtime tracing | Runtime infrastructure |

## Architectural red lines

La arquitectura se considerará violada si ocurre cualquiera de los siguientes casos:

* `Application` llama directamente `graph.invoke()`, `graph.ainvoke()` u otra API concreta de LangGraph;
* configuración de tenant contiene `StateGraph`, nodes, edges o tipos propios de LangGraph;
* un LangGraph node implementa directamente reglas empresariales o de autorización que deberían pertenecer a Domain/Application/Policy;
* Conversation o entidades de Domain persisten `GraphState`, `StateSnapshot` u otros objetos concretos del runtime;
* una policy empresarial se expresa exclusivamente mediante primitivas de branching de LangGraph y no mediante contratos propios del producto.

## Consequences

### Positive

* LangGraph puede ser sustituido sin rediseñar Domain o Application.
* El producto no presupone que Incubia será siempre el operador final.
* Las políticas pueden adaptarse por deployment y tenant sin modificar el runtime.
* Se evita mezclar reglas empresariales con mecanismos de ejecución.
* Los tests de aplicación pueden utilizar runtimes fake o in-memory.
* La evolución futura hacia otro runtime no cambia los contratos principales.
* El producto puede soportar Incubia Cloud, private cloud, customer-managed deployments u otros modelos futuros sin redefinir su core conceptual.

### Negative / Cost

* Se introduce una capa adicional de adaptación y mapping.
* Será necesario diseñar una jerarquía de políticas clara y verificable.
* No toda capacidad específica de LangGraph debe filtrarse automáticamente al contrato del producto.
* El diseño de `WorkflowRuntimePort` deberá mantenerse pequeño para evitar crear una copia abstracta de LangGraph.
* La neutralidad respecto al operador aumenta la necesidad de configuración explícita y validación de políticas.

## Alternatives considered

### LangGraph como dependencia directa de Application

Rechazado porque acoplaría los casos de uso a un framework específico.

### LangGraph como core del producto

Rechazado porque contradice la separación Hexagonal + DDD definida para el Orchestrator.

### Reglas empresariales centralizadas bajo una autoridad fija de Incubia

No adoptado como principio general porque impediría tratar el Orchestrator como un producto adaptable a distintos operadores, tenants y modelos de despliegue.

### Permitir que todo sea configurable por tenant

Rechazado porque comprometería invariantes de seguridad, aislamiento y consistencia del producto.

## Validation criteria

La decisión se considera correctamente implementada cuando:

* `domain/` no importa LangGraph;
* `application/` no importa LangGraph;
* existe `WorkflowRuntimePort`;
* `LangGraphRuntimeAdapter` implementa dicho contrato;
* los tipos específicos de LangGraph permanecen dentro del adapter/runtime;
* el primer workflow puede ejecutarse a través del puerto;
* las políticas no están hardcodeadas bajo el supuesto de que Incubia siempre es el operador;
* existe distinción conceptual entre Product/Kernel Invariants, Operator/Deployment Policy y Tenant/Business Policy;
* las reglas de tenant pueden variar sin modificar LangGraph ni el core del Orchestrator;
* los invariantes de producto no pueden ser anulados por configuración de tenant;
* el runtime recibe decisiones/contexto resueltos mediante contratos propios del producto.

## Follow-up decisions

Las siguientes decisiones ya no bloquean la aceptación de este ADR y se resolverán en ADRs especializados:

* modelo concreto de `WorkflowRuntimePort` y capacidades expuestas (`ADR-ORCH-007`);
* representación y combinación de `PolicyContext`, Product, Operator y Tenant policies (`ADR-ORCH-006`);
* persistencia y lifecycle de Conversation State vs runtime state (`ADR-ORCH-019`);
* definición concreta de pause/resume en contratos del producto;
* identificación del operador de un deployment y ownership de configuración.

Estas decisiones deberán respetar la frontera establecida en este ADR.

## Related

* SAD v1.1 — Incubia AI Orchestrator
* Draft — Estructura del repositorio `incubia-ai-orchestrator`
* ADR-ORCH-006 — Policy Engine & Guardrails
* ADR-ORCH-007 — Execution Contract independiente del runtime
* ADR-ORCH-019 — Separación entre Conversation State y GraphState

