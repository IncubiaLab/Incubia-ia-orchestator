<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-020-estrategia-de-tests-arquitectonicos-y-de-contratos-589739f90eac
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-020 — Estrategia de tests arquitectónicos y de contratos

**Status:** Proposed
**Scope:** `incubia-ai-orchestrator`

## Context

Las reglas de arquitectura del Orchestrator no deben existir solo en documentación. La separación entre Domain, Application, Ports, Adapters y runtimes puede degradarse con el tiempo si no existe verificación automática.

Además, puertos como `WorkflowRuntimePort` y `LLMPort` necesitan validación consistente entre distintas implementaciones.

## Decision

El repositorio separará pruebas en cuatro categorías:

```text
tests/
├── unit/
├── integration/
├── contract/
└── architecture/
```

### Unit

Validan Domain y Application sin infraestructura real.

### Integration

Validan adapters concretos y su interacción con frameworks/proveedores.

### Contract

Validan que distintas implementaciones cumplen el mismo puerto o contrato funcional.

Ejemplos iniciales:

```text
WorkflowRuntimePort
LLMPort
```

### Architecture

Validan reglas estructurales, incluyendo imports prohibidos y dirección de dependencias.

Como mínimo deberán impedir que `domain/` o `application/` dependan directamente de LangGraph, LangChain, OpenAI, FastAPI, SDKs de vector stores, canales o CRMs.

## Consequences

### Positive

* Las decisiones arquitectónicas pueden verificarse continuamente.
* Reduce regresiones de acoplamiento.
* Facilita introducir implementaciones alternativas de ports.
* Refuerza la capacidad de reemplazar frameworks y proveedores.

### Negative / Cost

* Aumenta el trabajo inicial de infraestructura de testing.
* Los tests arquitectónicos deberán actualizarse conscientemente cuando una decisión formal cambie mediante ADR.

## Alternatives considered

### Documentar reglas sin tests automáticos

Rechazado como estrategia principal porque las restricciones serían fáciles de romper accidentalmente.

### Solo tests unitarios e integración

Insuficiente para verificar límites arquitectónicos y compatibilidad de contratos entre adapters.

## Validation criteria

* Existen directorios `contract/` y `architecture/` desde la fase inicial.
* Al menos una regla automatizada impide imports de infraestructura desde Domain/Application.
* `LangGraphRuntimeAdapter` puede validarse contra el contrato de `WorkflowRuntimePort`.
* El OpenAI adapter puede probarse separadamente de los casos de uso.

## Related

* ADR-ORCH-001
* ADR-ORCH-007
* ADR-ORCH-013
* ADR-ORCH-018

