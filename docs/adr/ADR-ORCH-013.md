<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-013-llm-gateway-mediante-llmport-013214853adf
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-013 — LLM Gateway mediante LLMPort

**Status:** Proposed
**Scope:** `incubia-ai-orchestrator`

## Context

El Orchestrator necesita consumir modelos de IA sin acoplar Application o Domain a OpenAI ni a otro proveedor concreto. El SAD define un LLM Gateway abstracto y contempla múltiples proveedores futuros.

## Decision

El acceso a modelos se realizará mediante un puerto propio `LLMPort`.

La primera implementación prevista será un adapter de OpenAI, ubicado fuera de Application y Domain.

```text
Application / Runtime Node
        │
        ▼
      LLMPort
        ▲
        │
 OpenAIAdapter
```

El proveedor concreto se resolverá en bootstrap/composition root.

## Consequences

### Positive

* OpenAI no se convierte en dependencia estructural.
* Se habilita sustitución futura por modelos locales, open-weight o proveedores alternativos.
* Los tests pueden utilizar fake LLMs.
* Permite introducir routing de modelos posteriormente sin modificar los consumidores principales.

### Negative / Cost

* No todas las capacidades específicas de un proveedor deben exponerse automáticamente por el puerto.
* Se requiere mapping entre request/response de Incubia y SDKs externos.

## Alternatives considered

### OpenAI SDK directamente en Application

Rechazado por acoplamiento directo al proveedor.

### Crear desde el inicio un router multi-provider complejo

No adoptado para el primer slice. El puerto debe permitir esa evolución sin implementar complejidad antes de necesitarla.

## Validation criteria

* `application/` y `domain/` no importan `openai`.
* Existe `LLMPort`.
* El OpenAI adapter implementa el contrato.
* El adapter concreto se inyecta desde bootstrap.

## Related

* ADR-ORCH-001 — LangGraph como runtime reemplazable
* Draft — Estructura del repositorio `incubia-ai-orchestrator`

