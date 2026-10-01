<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-019-separacion-entre-conversation-state-y-graphstate-de6cbca510e0
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-019 — Separación entre Conversation State y GraphState

**Status:** Proposed
**Scope:** `incubia-ai-orchestrator`

## Context

El sistema necesita representar conceptos propios de Incubia, como conversación y ejecución, al mismo tiempo que LangGraph necesita su propio estado operativo para ejecutar el workflow.

Si ambos conceptos se fusionan, tipos y decisiones internas de LangGraph pueden propagarse hacia el dominio y dificultar el reemplazo del runtime.

## Decision

`Conversation State` y `GraphState` serán conceptos distintos.

* El estado de conversación pertenece al modelo de Incubia y podrá evolucionar dentro del bounded context `conversation`.
* `GraphState` pertenece exclusivamente al adapter de LangGraph.
* Un mapper traducirá entre contratos/estado de Incubia y el estado requerido por el runtime.

```text
ExecutionRequest / Conversation data
          ↓
   GraphStateMapper
          ↓
      GraphState
          ↓
      LangGraph
          ↓
      GraphState
          ↓
   GraphStateMapper
          ↓
   ExecutionResult
```

Ubicación prevista:

```text
modules/orchestration/adapters/runtime/langgraph/
├── state.py
└── mapper.py
```

## Consequences

### Positive

* El modelo de conversación no queda condicionado por LangGraph.
* El estado del workflow puede optimizarse para ejecución sin contaminar el dominio.
* Facilita sustituir el runtime.
* Hace explícitas las transformaciones entre modelos.

### Negative / Cost

* Se requiere mantener mappings adicionales.
* Puede existir duplicación parcial de campos entre ambos estados.

## Alternatives considered

### Utilizar `GraphState` como modelo de conversación global

Rechazado porque convierte una estructura del runtime en parte del modelo de dominio.

### Compartir un único DTO mutable para todas las capas

Rechazado porque difumina límites y aumenta acoplamiento.

## Validation criteria

* `GraphState` solo existe dentro del adapter LangGraph.
* `conversation` no importa tipos de LangGraph.
* Las conversiones runtime ↔ contratos Incubia están centralizadas en un mapper explícito.

## Related

* ADR-ORCH-001
* ADR-ORCH-007
* ADR-ORCH-017

