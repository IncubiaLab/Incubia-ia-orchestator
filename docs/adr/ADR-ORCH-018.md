<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-018-regla-de-dependencias-y-composition-root-51a80e712bf0
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-018 — Regla de dependencias y Composition Root

**Status:** Proposed
**Scope:** `incubia-ai-orchestrator`

## Context

La arquitectura Hexagonal + DDD solo se mantiene si las dependencias apuntan hacia contratos y lógica interna, no desde el dominio hacia frameworks e infraestructura.

Además, las implementaciones concretas necesitan un punto explícito donde ensamblarse.

## Decision

Se adopta la siguiente dirección conceptual de dependencias:

```text
Adapters / Interfaces
        ↓
Application
        ↓
Domain
```

Los puertos/contracts pertenecen a las fronteras internas y son implementados por adapters externos.

Las siguientes dependencias quedan prohibidas dentro de `domain/` y `application/` salvo que un ADR futuro justifique una excepción:

```text
langgraph
langchain
openai
fastapi
qdrant
redis
SDKs de canales o CRMs
```

La selección y construcción de implementaciones concretas se realizará exclusivamente en `bootstrap/`, que actuará como Composition Root.

Ejemplo:

```text
bootstrap/
├── settings.py
├── container.py
└── app.py
```

`bootstrap` podrá conocer tanto puertos como adapters concretos para construir el grafo de dependencias.

## Consequences

### Positive

* La dirección de dependencias queda explícita.
* Frameworks y proveedores permanecen reemplazables.
* Los casos de uso pueden probarse con fakes.
* La composición del sistema está centralizada y auditable.

### Negative / Cost

* Requiere disciplina de imports.
* El Composition Root puede crecer y deberá modularizarse si la cantidad de dependencias aumenta.

## Alternatives considered

### Instanciación distribuida dentro de controllers, services y nodes

Rechazado porque dispersa configuración, dificulta testing y acopla capas internas a implementaciones concretas.

### Service Locator global

No adoptado porque oculta dependencias y dificulta entender el grafo real de composición.

## Validation criteria

* Las implementaciones concretas se construyen desde `bootstrap/`.
* Application recibe dependencias por interfaces/ports.
* Tests de arquitectura detectan imports prohibidos.
* Los controllers y nodes no crean directamente clientes externos cuando existe un adapter definido.

## Related

* ADR-ORCH-001
* ADR-ORCH-013
* ADR-ORCH-017

