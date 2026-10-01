<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-017-estructura-module-first-y-bounded-context-first-c905b17b13a2
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-017 — Estructura module-first y bounded-context-first

**Status:** Proposed
**Scope:** `incubia-ai-orchestrator`

## Context

El repositorio debe reflejar Hexagonal + DDD sin caer en una estructura global por capas que termine mezclando múltiples bounded contexts dentro de carpetas únicas como `domain/`, `application/` o `infrastructure/`.

El SAD identifica inicialmente contextos como AI Orchestration, Conversation, Identity & Tenant, Knowledge, Sales, Support, Reporting y Audit.

## Decision

El código se organizará primero por módulo/bounded context y luego por capas internas.

```text
src/incubia_orchestrator/
├── foundation/
├── modules/
│   ├── orchestration/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── ports/
│   │   └── adapters/
│   ├── conversation/
│   ├── identity_tenant/
│   ├── knowledge/
│   ├── sales/
│   ├── support/
│   ├── reporting/
│   └── audit/
├── interfaces/
└── bootstrap/
```

Los bounded contexts serán módulos internos del mismo repositorio mientras no exista una razón operativa para extraerlos a servicios/repositorios independientes.

## Consequences

### Positive

* Los límites de negocio son visibles desde el árbol del repositorio.
* Cada módulo puede aplicar internamente Domain / Application / Ports / Adapters.
* Reduce el riesgo de un `domain/` global con responsabilidades mezcladas.
* Permite evolucionar hacia extracción selectiva de contextos sin imponer microservicios prematuros.

### Negative / Cost

* Puede existir repetición estructural entre módulos.
* Requiere disciplina para evitar dependencias directas entre internals de bounded contexts.

## Alternatives considered

### Layer-first global

```text
domain/
application/
infrastructure/
```

Rechazado como estructura principal porque oculta los bounded contexts y favorece dependencias transversales entre funcionalidades no relacionadas.

### Un repositorio por bounded context desde el MVP

Rechazado por complejidad operativa prematura.

## Validation criteria

* `orchestration` nace como módulo independiente.
* Nuevos contextos se agregan bajo `modules/`.
* Un módulo no importa internals privados de otro sin contrato explícito.
* La extracción a otro repositorio se decide por deploy, lifecycle, persistencia, escalamiento o ownership independientes, no solo por existir un bounded context.

## Related

* Draft — Estructura del repositorio `incubia-ai-orchestrator`
* SAD v1.1 — Bounded Contexts iniciales

