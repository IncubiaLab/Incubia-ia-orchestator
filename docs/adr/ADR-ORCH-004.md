<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-004-agent-discovery-y-agent-registry-283ae36c62e5
Sincronizado desde Linear el 2026-10-06. Estado conservado del documento de origen. -->

# ADR-ORCH-004 — Agent Discovery y Agent Registry

**Status:** Accepted
**Scope:** `incubia-ai-orchestrator`

## Context

Tras `ADR-ORCH-003`, el Router resuelve una `CapabilityRequirement` sin conocer nombres concretos de agentes, tools, graphs, modelos o proveedores. El siguiente problema arquitectónico es descubrir qué agentes pueden satisfacer esa capability dentro del deployment y tenant actuales sin introducir hardcoding en el Router.

El foco de este ADR es el descubrimiento de agentes. El modelo interno de ejecución y razonamiento de los agentes queda explícitamente fuera de alcance y se definirá en un ADR posterior.

## Decision

Se separan conceptualmente `Agent Registry`, `Agent Discovery` y `Agent Selection`.

```text
CapabilityRequirement
        ↓
AgentDiscoveryPort
        ↓
AgentCandidateSet
        ↓
Agent Selection
        ↓
Selected Agent
```

### Agent Registry

El Registry mantiene el inventario de agentes conocidos por una instalación.

Responde principalmente a:

> ¿Qué agentes conoce el sistema?

### Agent Discovery

Discovery resuelve qué agentes registrados son candidatos técnicamente válidos para una necesidad concreta.

Responde principalmente a:

> ¿Qué agentes pueden satisfacer esta capability dentro del scope actual?

### Agent Selection

Selection decide cuál de los candidatos elegibles será utilizado.

Responde principalmente a:

> ¿Cuál de los candidatos elegibles se utilizará para esta ejecución?

Discovery y Selection permanecen conceptualmente separados, aunque el MVP pueda utilizar una selección determinista simple.

## AgentDescriptor

Cada agente expondrá un descriptor framework-neutral.

Conceptualmente:

```text
AgentDescriptor
├── agent_id
├── name
├── version
├── capabilities[]
├── technical_requirements[]
├── input_modes[]
├── output_modes[]
├── execution_mode
├── deployment_scope
├── tenant_scope
├── policy_tags[]
├── status
└── metadata controlada
```

El descriptor describe al agente, pero no contiene lógica de routing ni secretos.

## Capability como clave de discovery

La principal clave semántica para el discovery será `CapabilityId`.

```text
ADR-ORCH-003
Request → CapabilityRequirement

ADR-ORCH-004
CapabilityRequirement → Agent Candidates
```

El Router no conocerá agentes concretos.

Quedan prohibidos patrones como:

```text
if capability == X:
    return AgentY
```

en Router/Application.

## AgentDiscoveryPort

Application dependerá de un contrato propio del producto:

```python
class AgentDiscoveryPort(Protocol):
    async def discover(
        self,
        query: AgentDiscoveryQuery,
    ) -> AgentCandidateSet:
        ...
```

`AgentDiscoveryQuery` podrá transportar conceptualmente:

```text
capability
deployment_id
tenant_id
technical_requirements
input_mode
output_mode
```

No transportará policies completas ni tipos específicos de frameworks.

## AgentRegistryPort

El inventario podrá exponerse mediante un contrato separado para necesidades de administración/bootstrap:

```text
register
remove
get
list
```

Los casos de uso de routing no deberán implementar discovery recorriendo directamente `list_all()` del registry.

## Discovery pipeline

El discovery filtrará candidatos aproximadamente en este orden:

```text
Registered Agents
      ↓
Status
      ↓
Deployment Scope
      ↓
Tenant Scope
      ↓
Capability Match
      ↓
Technical Compatibility
      ↓
Policy Eligibility
      ↓
AgentCandidateSet
```

El discovery produce candidatos; no concede autorización definitiva.

Las operaciones protegidas continúan sujetas a `PolicyEnginePort` según `ADR-ORCH-006`.

## Scope multi-tenant

Un agente podrá declarar alcance:

```text
GLOBAL
DEPLOYMENT
TENANT
```

Un agente fuera del scope efectivo de deployment/tenant nunca podrá aparecer en el conjunto de candidatos.

## Discovery vs Policy

Encontrar un agente compatible significa únicamente que es un candidato técnico.

```text
Discovery
   ↓
Candidate
   ↓
Policy Enforcement
   ↓
ALLOW / DENY / REQUIRE_APPROVAL
```

Discovery no reemplaza autorización.

## Discovery devuelve conjuntos

El contrato no será:

```text
discover(capability) -> Agent
```

sino conceptualmente:

```text
discover(query) -> AgentCandidateSet
```

Esto permite coexistencia de múltiples implementaciones y versiones para una misma capability.

## MVP: registro in-process

La primera implementación será local/in-process con registro explícito desde el Composition Root.

Conceptualmente:

```text
bootstrap
   ↓
register descriptors/factories
   ↓
InMemoryAgentRegistry
   ↓
AgentDiscoveryAdapter
```

El registro inicial puede ser estático sin que el routing sea estático.

Los agentes no deberán autorregistrarse mediante side effects globales.

## Identidad y versionado

Se distinguen:

```text
agent_id
agent_version
agent_instance_id
```

`agent_id` identifica la definición lógica del agente.

`agent_version` identifica una versión de dicha definición.

`agent_instance_id` identifica una instancia de ejecución/deployment cuando sea necesario.

Versiones diferentes podrán coexistir. Una ejecución que ya seleccionó un agente deberá conservar la versión seleccionada cuando sea relevante para resume/reproducibilidad.

## Estados mínimos

El descriptor podrá utilizar al menos:

```text
ACTIVE
DISABLED
DEPRECATED
UNAVAILABLE
```

Discovery no devolverá agentes incompatibles con el estado requerido por la ejecución.

## Secretos

`AgentDescriptor` nunca almacenará secretos como API keys, passwords o tokens.

El descriptor podrá indicar requisitos o esquemas de autenticación, mientras las credenciales permanecen detrás de mecanismos dedicados de secrets/credentials.

## Interoperabilidad futura

El modelo interno se diseñará para ser conceptualmente mapeable a mecanismos externos de agent discovery, incluyendo futuros adapters basados en A2A Agent Cards u otros registries.

No se adopta A2A como dependencia obligatoria en este ADR.

Conceptualmente:

```text
Incubia AgentDescriptor
        ↕ mapper
External Agent Card / Registry
```

## Sin semantic discovery en el MVP

El Agent Discovery no volverá a interpretar lenguaje natural.

`ADR-ORCH-003` ya es responsable de resolver lenguaje natural hacia capabilities.

Por tanto, el MVP utilizará structured/exact capability matching y filtros explícitos.

## Out of scope

Este ADR no define:

* modelo interno de agentes;
* prompting o reasoning de agentes;
* agent-to-agent handoff;
* tool ownership detallado;
* load balancing avanzado;
* multi-agent planning;
* protocolo A2A obligatorio.

Estas decisiones se tratarán en ADRs posteriores.

## Architectural red lines

```text
❌ Router importa agentes concretos.
❌ Routing utiliza if capability == X → AgentY.
❌ Un agente se autorregistra globalmente mediante side effects.
❌ Discovery expone agentes fuera del deployment/tenant scope.
❌ Discovery se interpreta como autorización.
❌ El descriptor contiene secretos.
❌ El discovery vuelve a clasificar lenguaje natural que ya resolvió ORCH-003.
```

## Consequences

### Positive

* El Router permanece desacoplado de implementaciones de agentes.
* Nuevos agentes pueden incorporarse sin modificar routing.
* Se soportan múltiples agentes/versiones por capability.
* El modelo es compatible con escenarios multi-tenant y customer-specific agents.
* Se preserva una vía de evolución hacia registries distribuidos y protocolos externos.
* Discovery puede probarse independientemente de ejecución de agentes.

### Negative / Cost

* Introduce descriptors, registry y discovery como conceptos adicionales.
* Requiere disciplina para evitar trasladar lógica de Selection al Discovery.
* El versionado y scope deberán mantenerse consistentes durante el ciclo de vida de las ejecuciones.

## Validation criteria

La decisión se considera correctamente implementada cuando:

* Router/Application no importa agentes concretos para resolver capabilities;
* existe `AgentDiscoveryPort`;
* cada agente registrable tiene un `AgentDescriptor`;
* discovery devuelve `AgentCandidateSet`;
* deployment y tenant scope se respetan;
* agentes disabled no son candidatos;
* policies pueden restringir candidatos sin que Discovery se convierta en Policy Engine;
* la primera implementación funciona con un registry in-process;
* no existen secretos en descriptors;
* el modelo interno de agentes permanece fuera de este ADR.

## Related

* ADR-ORCH-003 — Capability-first routing con Decision Model especializado
* ADR-ORCH-006 — Policy Engine & Guardrails
* ADR-ORCH-007 — Execution Contract independiente del runtime
* ADR-ORCH-018 — Regla de dependencias y Composition Root
* ADR-ORCH-011 — Handoff Agent → Agent (futuro)
* ADR-ORCH-016 — Integración futura con runtimes multiagente

