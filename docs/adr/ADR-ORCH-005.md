<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-005-tool-registry-tool-discovery-y-frontera-de-ejecucion-eaddcd74eb07
Sincronizado desde Linear el 2026-10-06. Estado conservado del documento de origen. -->

# ADR-ORCH-005 — Tool Registry, Tool Discovery y frontera de ejecución

**Status:** Accepted
**Scope:** `incubia-ai-orchestrator`

## Context

Tras `ADR-ORCH-003` y `ADR-ORCH-004`, el Orchestrator ya puede resolver una capability y descubrir agentes elegibles sin hardcoding. Falta definir cómo los agentes y workflows acceden a capacidades externas sin saltarse gobernanza, auditoría o controles de side effects.

El foco de este ADR es definir la frontera de Tool Registry, Tool Discovery y Tool Execution. Las políticas específicas de mutation safety, human approval, retries, compensaciones e idempotency enforcement se separan en un ADR posterior (`ADR-ORCH-021`).

## Decision

Toda operación externa ejecutable por agentes o workflows se modelará como una `Tool` registrada y descrita mediante contratos propios del producto.

Los agentes y workflows no accederán directamente a SDKs, APIs externas, bases de datos ni clientes de integración.

```text
Agent / Workflow
      │
      ▼
ToolDiscoveryPort
      │
      ▼
ToolCandidateSet
      │
      ▼
Policy Enforcement
      │
      ▼
ToolExecutorPort
      │
      ▼
Tool Adapter
      │
      ▼
External System
```

Se separan tres responsabilidades:

* `ToolRegistry`: inventario de tools conocidas;
* `ToolDiscovery`: resolución de tools candidatas para una capability/contexto;
* `ToolExecutor`: ejecución de una tool concreta ya seleccionada y autorizada.

## ToolDescriptor

Cada tool publicará un `ToolDescriptor` framework-neutral.

El descriptor deberá incluir como mínimo:

* `tool_id` estable;
* `tool_version`;
* capabilities soportadas;
* input schema;
* output schema;
* scope de deployment/tenant;
* operación/tipo de side effect;
* semantics de idempotencia;
* reversibilidad;
* indicador destructivo;
* estado de disponibilidad;
* referencia de perfil de credenciales sin secretos.

Ejemplo conceptual:

```yaml
tool_id: crm.customer.update
version: 1.2
capabilities:
  - crm.customer.update
operation_type: MUTATION
destructive: false
idempotency: CONDITIONAL
reversibility: REVERSIBLE
```

Los descriptors son información declarativa. No constituyen autorización.

## Clasificación inicial de operations

Se adoptan tres clases iniciales:

```text
READ
MUTATION
EXTERNAL_ACTION
```

### READ

Consulta información sin modificar estado persistente.

Ejemplos:

* `customer.get`
* `sales.summary`
* `inventory.search`
* `ticket.list`

### MUTATION

Modifica estado persistente controlado.

Ejemplos:

* `customer.update`
* `ticket.create`
* `order.cancel`

### EXTERNAL_ACTION

Produce un efecto en un sistema o mundo externo cuya reversibilidad no controla completamente el Orchestrator.

Ejemplos:

* `email.send`
* `sms.send`
* `payment.capture`
* `shipment.create`

La clasificación describe semántica de la tool. Las consecuencias de seguridad y policy se definen en `ADR-ORCH-021`.

## Side-effect metadata

Toda Tool no read-only deberá declarar explícitamente:

```text
operation_type
destructive
idempotency_semantics
reversibility
```

Idempotency se modelará al menos mediante:

```text
IDEMPOTENT
NON_IDEMPOTENT
IDEMPOTENT_WITH_KEY
UNKNOWN
```

No se inferirá automáticamente a partir del método HTTP o SDK utilizado.

## Tool call identity

Cada ejecución de una Tool tendrá un `tool_call_id` separado de `execution_id`.

```text
execution_id
   ├── tool_call_id: tc-001
   ├── tool_call_id: tc-002
   └── tool_call_id: tc-003
```

Este identificador será la base para tracing, audit, retries e idempotency cuando aplique.

Para operaciones `IDEMPOTENT_WITH_KEY`, adapters podrán derivar o asociar una idempotency key basada en identificadores controlados por el producto, por ejemplo `execution_id + tool_call_id`.

## Tool Discovery

`ToolDiscoveryPort` devolverá un `ToolCandidateSet`, no una única implementación.

```text
CapabilityRequirement
        ↓
ToolDiscoveryPort
        ↓
ToolCandidateSet
```

Puede haber varias implementaciones de una misma capability según deployment o tenant.

Discovery deberá respetar como mínimo:

* deployment scope;
* tenant scope;
* enabled integrations;
* status/availability;
* capability compatibility;
* technical compatibility;
* policy eligibility.

Discovery no concede autorización; solo identifica candidatos técnicamente elegibles.

## Tool execution

El LLM o Agent puede proponer una `ToolInvocationRequest`, pero no ejecutar el side effect directamente.

```text
LLM / Agent
      │
      │ proposes
      ▼
ToolInvocationRequest
      │
      ▼
Tool Resolution
      │
      ▼
Policy Enforcement
      │
      ▼
ToolExecutorPort
```

Se prohíbe que un agente importe directamente un SDK externo para ejecutar operaciones fuera del Tool Layer.

## ToolExecutionResult

La ejecución devolverá un contrato tipado propio del producto.

Conceptualmente:

```text
ToolExecutionResult
├── tool_call_id
├── tool_id
├── status
├── output
├── error
└── external_reference
```

Estados iniciales:

```text
SUCCESS
FAILED
PARTIAL
```

`external_reference` deberá conservarse cuando el sistema externo genere un identificador relevante, por ejemplo un case ID, order ID o payment reference.

## Credentials

Los ToolDescriptors no contendrán secretos.

No se permiten en descriptors:

* API keys;
* passwords;
* access tokens;
* client secrets.

Los descriptors podrán referenciar un `credential_profile` o mecanismo equivalente cuya resolución corresponderá a infraestructura/credential provider.

## Relationship with Policy Engine

Tool metadata describe propiedades; `PolicyEnginePort` determina si una ejecución está permitida y bajo qué condiciones.

```text
ToolDescriptor
+
Execution Scope
+
Policy Context
=
PolicyDecision
```

Las reglas concretas para mutations, approvals, retries, idempotency enforcement y compensating actions se definen fuera de este ADR.

## Mutation policy boundary

Este ADR no decide:

* cuándo una mutation requiere human approval;
* qué risk class corresponde a una operación;
* qué mutations pueden reintentarse;
* dry-run requirements;
* confirmation flows;
* optimistic concurrency;
* rollback;
* compensating actions;
* exactly-once / at-least-once semantics;
* reglas de retry para side effects.

Estas decisiones pertenecen a `ADR-ORCH-021 — Mutation Tool Safety & Side-Effect Policy` y, donde aplique, `ADR-ORCH-015 — Fallbacks, retries y timeouts`.

## Protocol compatibility

Los contratos propios del producto podrán mapearse en el futuro a protocolos externos como MCP.

Incubia no adoptará un protocolo externo como arquitectura interna del Tool Layer. Annotations o metadata de un protocolo serán tratadas como hints/descripciones y no como autorización.

## Consequences

### Positive

* Agents no pueden saltarse Governance usando SDKs directos.
* Discovery y ejecución permanecen desacoplados de implementaciones específicas.
* Side effects son observables y auditables mediante `tool_call_id`.
* Mutation semantics quedan explícitas desde el descriptor.
* Los adapters por tenant/deployment pueden variar sin cambiar el Router o Agent.
* Facilita integración futura con MCP u otros protocolos sin acoplar el core.

### Negative / Cost

* Introduce mapping adicional entre Tool contracts y SDKs externos.
* Requiere mantener descriptors y schemas versionados.
* El control correcto de mutations exige un ADR adicional y enforcement consistente.

## Red lines

Se consideran violaciones de arquitectura:

```text
Agent imports external SDK directly
LLM executes side effects directly
Mutation tool without declared side-effect semantics
Retry de mutations decidido únicamente por LangGraph
ToolDescriptor tratado como autorización
Credentials almacenadas dentro de ToolDescriptor
```

## Validation criteria

La decisión se considera correctamente implementada cuando:

* existe `ToolDiscoveryPort`;
* existe `ToolExecutorPort`;
* tools se describen mediante contratos propios;
* discovery devuelve candidate sets;
* agents/workflows no ejecutan integraciones externas directamente;
* toda mutation declara side-effect metadata;
* existe `tool_call_id` por invocación;
* secrets no forman parte de ToolDescriptor;
* policy enforcement ocurre antes de ejecutar operaciones protegidas;
* mutation safety avanzada permanece fuera de este ADR.

## Related

* ADR-ORCH-003 — Capability-first routing
* ADR-ORCH-004 — Agent Discovery y Agent Registry
* ADR-ORCH-006 — Policy Engine & Guardrails
* ADR-ORCH-007 — Execution Contract
* ADR-ORCH-015 — Fallbacks, retries y timeouts
* ADR-ORCH-021 — Mutation Tool Safety & Side-Effect Policy

