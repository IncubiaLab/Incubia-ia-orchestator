# Spec 01 — Estructura y dependencias

## Objetivo

Organizar el repositorio por bounded context y mantener las dependencias hacia contratos y lógica interna.

## Estructura del primer slice

```text
src/incubia_orchestrator/
├── foundation/contracts/          # contratos de ejecución compartidos
├── modules/orchestration/
│   ├── application/use_cases/      # HandleMessage
│   ├── ports/                      # WorkflowRuntimePort y LLMPort
│   └── adapters/
│       ├── runtime/langgraph/nodes/
│       └── llm/openai/
├── interfaces/http/routes/         # endpoint de mensajes
└── bootstrap/                      # settings, container y app
tests/{unit,integration,contract,architecture}/
docs/{adr,specs}/
```

`orchestration/domain/` se añade cuando haya reglas de dominio propias; no es necesario para el primer mensaje. Los contextos `conversation`, `identity_tenant`, `knowledge`, `sales`, `support`, `reporting` y `audit` se agregan bajo `modules/` al implementar sus capacidades.

## Reglas

- `foundation/` contiene solo contratos e identificadores usados por más de un contexto; no contiene utilidades genéricas.
- `domain/` no importa `application/`, adapters, interfaces, frameworks ni SDKs.
- `application/` conoce puertos y contratos propios; no importa LangGraph, OpenAI, FastAPI, LangChain, Qdrant, Redis ni SDKs de canales o CRM.
- Adapters implementan puertos y traducen tipos externos a tipos del producto.
- Los módulos no importan internals privados de otros contextos; usan contratos explícitos.
- `bootstrap/` es el único lugar que selecciona e instancia implementaciones concretas.
- Un bounded context no se convierte automáticamente en otro repositorio o servicio.

## Criterios de aceptación

- La ruta de LangGraph es `modules/orchestration/adapters/runtime/langgraph/`.
- El código del primer slice se ubica en las carpetas anteriores.
- Una prueba arquitectónica impide imports de infraestructura desde Domain/Application.
- Nuevos contextos se incorporan bajo `modules/` con ownership claro.

## Fuentes

[ADR-ORCH-017](https://linear.app/hector-cruz/document/adr-orch-017-estructura-module-first-y-bounded-context-first-c905b17b13a2) (propuesto), [ADR-ORCH-018](https://linear.app/hector-cruz/document/adr-orch-018-regla-de-dependencias-y-composition-root-51a80e712bf0) (propuesto), [borrador de estructura](https://linear.app/hector-cruz/document/draft-estructura-del-repositorio-incubia-ai-orchestrator-084204cfd1bf).
