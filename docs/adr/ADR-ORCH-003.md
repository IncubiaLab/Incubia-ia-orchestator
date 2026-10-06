<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-003-capability-first-routing-con-decision-model-especializado-fb1686ec1b4f
Sincronizado desde Linear el 2026-10-06. Estado conservado del documento de origen. -->

# ADR-ORCH-003 — Capability-first routing con Decision Model especializado

**Status:** Accepted
**Scope:** `incubia-ai-orchestrator`

## Context

El Orchestrator necesita resolver solicitudes de lenguaje natural hacia capacidades ejecutables sin acoplar el routing a nombres de agentes, tools, graphs, modelos o proveedores concretos.

El SAD ya distingue intent y capabilities, y establece que el Router debe considerar intent, capabilities, policies, tenant y contexto. Sin embargo, para un producto adaptable a múltiples clientes, el intent no debe convertirse en la unidad arquitectónica estable de routing.

Adicionalmente, se adopta una invariante de arquitectura: la clasificación semántica primaria para routing deberá ejecutarse mediante un **Decision Model especializado**, separado del LLM generativo principal, detrás de un puerto propio del producto.

JEV, Laya u otros modelos equivalentes se consideran implementaciones posibles de ese puerto, no parte de la arquitectura conceptual.

## Decision

Incubia adopta **capability-first routing con intent-assisted understanding**.

El intent representa una hipótesis semántica sobre lo que el usuario parece querer. La capability representa la unidad estable que el sistema utiliza para decidir qué comportamiento necesita ejecutar.

El pipeline conceptual será:

```text
Request
   ↓
Scope Resolution
   ↓
Eligible Capability Set
   ↓
DecisionModelPort
   ↓
Intent / Capability Signals
   ↓
Capability Resolver
   ↓
RouteDecision
   ↓
Policy Engine
   ↓
Execution Planner
   ↓
WorkflowRuntimePort
```

## Invariante de arquitectura — Decision Model especializado

La clasificación semántica primaria utilizada por el Router deberá ejecutarse mediante un contrato propio del producto:

```text
DecisionModelPort
        ▲
        │
  ┌─────┼───────────────┐
  │     │               │
Jev  LayaAdapter   FutureDecisionModelAdapter
```

El LLM generativo principal no será el classifier primario del routing mientras exista un Decision Model especializado disponible que cumpla los requisitos de calidad, latencia y operación del deployment.

La selección concreta entre JEV, Laya u otro proveedor/modelo no queda fijada por este ADR. Esa elección deberá basarse en benchmarking de calidad, latencia, costo, despliegue y requisitos de privacidad.

## Separación de responsabilidades de modelos

```text
DecisionModelPort
├── intent classification
├── capability classification
├── scoring
├── semantic gates
└── risk / routing signals

LLMPort
├── reasoning
├── generation
├── synthesis
├── conversation
└── interpretación compleja cuando corresponda
```

El Decision Model produce señales probabilísticas. No concede autorización.

## Intent vs Capability

### Intent

Responde:

> ¿Qué parece querer el usuario?

Ejemplo:

```text
sales.pricing_information
```

Puede incluir confidence, entidades extraídas y otras señales observables.

### Business Capability

Responde:

> ¿Qué comportamiento de negocio necesita ejecutar el producto?

Ejemplo:

```text
sales.pricing.read
```

La capability es la unidad principal de routing.

### Technical Requirements

Las capacidades técnicas permanecen separadas de las business capabilities.

Ejemplo:

```text
Business capability:
reporting.sales_summary

Technical requirements:
- structured_data
- analytics
- response_generation
```

## Eligible Capability Set

El Decision Model no evaluará indiscriminadamente todas las capacidades existentes del producto.

Antes de la clasificación se construirá el conjunto elegible según deployment, tenant y restricciones aplicables:

```text
Available Capabilities
∩ Deployment Constraints
∩ Tenant Configuration
= Eligible Capabilities
```

La resolución posterior de autorización permanece responsabilidad de `ADR-ORCH-006 — Policy Engine & Guardrails`.

## RouteDecision

El Router no devuelve agentes, tools, models, graph names ni nodes concretos.

Conceptualmente devuelve información runtime-neutral, por ejemplo:

```text
RouteDecision
- primary_capability
- supporting_capabilities / technical_requirements
- intent_signals
- confidence
- routing_status
```

Los estados mínimos de routing serán:

```text
RESOLVED
AMBIGUOUS
UNSUPPORTED
```

`FORBIDDEN` no pertenece al Router; es una decisión de Policy.

## Routing determinista antes que probabilístico

Cuando exista suficiente señal determinista, se evitará invocar el Decision Model.

Ejemplos:

* endpoint o comando que ya declara capability;
* contexto de aplicación que ya fija la operación;
* workflow interno con capability conocida.

Cuando se requiera interpretación semántica, se utilizará `DecisionModelPort`.

## Fallback por incertidumbre

El Decision Model podrá producir confidence o señales equivalentes.

La política concreta de thresholds no queda fijada por este ADR y deberá calibrarse mediante evaluación sobre datasets representativos.

Conceptualmente:

```text
High confidence
    → capability resolution

Medium confidence
    → secondary reasoning / validation

Low confidence
    → clarification / unsupported
```

El fallback puede incluir LLM reasoning o solicitud de aclaración, pero nunca debe transformar confidence en autorización.

## Multi-capability

El modelo conceptual permitirá múltiples capabilities, aunque el MVP optimice inicialmente el caso común:

```text
1 request → 1 primary business capability
```

La estructura debe permitir evolución futura hacia:

```text
1 request → N business capabilities
```

sin rediseñar el Router.

## Primary vs Supporting

Se distingue entre:

```text
Primary Business Capability
```

y:

```text
Supporting Capabilities / Technical Requirements
```

para evitar que el resultado del Router se convierta en una colección sin semántica.

## Router vs Planner

El Router responde:

> ¿Qué capability necesita la solicitud?

El Planner responde:

> ¿Cómo se materializa o combina esa capability durante la ejecución?

Ambas responsabilidades pueden compartir implementación durante el MVP, pero permanecen conceptualmente separadas.

## Relación con Policy

Las señales del Decision Model pueden alimentar `PolicyContext`, por ejemplo:

```text
risk_signal = HIGH
possible_data_export = true
mutation_intent = true
```

Sin embargo, el Decision Model nunca produce autoridad efectiva.

Regla:

```text
Probabilistic Signal
        ↓
Policy Engine
        ↓
Deterministic Consequence
```

Ejemplo:

```text
Decision Model:
risk = HIGH

Policy Engine:
REQUIRE_APPROVAL
```

Nunca:

```text
Decision Model:
ALLOW
→ execute mutation
```

La delegación nunca aumenta autoridad.

## Reproducibilidad

No se considera a JEV/Laya "idempotentes" en sentido matemático como propiedad arquitectónica.

La arquitectura buscará reproducibilidad fijando cuando sea necesario:

* model/provider;
* model version/checkpoint;
* candidate set;
* decision schema;
* threshold configuration;
* policy revision.

## Consequences

### Positive

* desacopla routing del LLM generativo principal;
* reduce costo y latencia en decisiones acotadas cuando el Decision Model resulta adecuado;
* mantiene intent como señal útil sin convertir taxonomía lingüística en arquitectura;
* capability funciona como lenguaje común entre tenants con vocabularios distintos;
* evita acoplamiento directo entre Router y Agent Registry;
* permite proveedores diferentes de Decision Model según deployment;
* mejora testabilidad del routing mediante un contrato especializado;
* mantiene autorización separada de clasificación probabilística.

### Negative / Cost

* introduce un nuevo puerto y familia de adapters;
* requiere datasets de evaluación representativos para calibrar classifier y thresholds;
* será necesario gestionar versiones de modelos y schemas de decisión;
* errores del classifier pueden afectar routing y requieren fallback controlado;
* coexistirán `DecisionModelPort` y `LLMPort`, aumentando ligeramente la superficie arquitectónica.

## Alternatives considered

### Intent-first routing

No adoptado como unidad principal porque produce taxonomías frágiles y puede explotar combinatoriamente al crecer solicitudes compuestas.

### Capability-first sin intent

No adoptado porque intent sigue siendo una señal valiosa para comprensión semántica, observabilidad y analytics.

### LLM generativo como classifier primario

No adoptado como estrategia principal porque mezcla generación/razonamiento con decisiones acotadas de routing y aumenta costo, latencia y acoplamiento.

### Acoplar directamente JEV o Laya al Router

Rechazado porque convertiría una implementación concreta en dependencia estructural.

## Validation criteria

La decisión se considera correctamente implementada cuando:

* existe `DecisionModelPort` independiente de JEV/Laya;
* Router no retorna nombres concretos de agents, tools, graphs, models o providers;
* las capabilities son la unidad principal de routing;
* intent permanece como señal semántica, no como autoridad de ejecución;
* el conjunto de capabilities candidatas puede limitarse por deployment/tenant;
* authorization continúa pasando por `PolicyEnginePort`;
* confidence del classifier nunca concede permisos;
* existen outcomes `RESOLVED`, `AMBIGUOUS` y `UNSUPPORTED`;
* routing determinista puede evitar el Decision Model cuando la capability ya es conocida;
* el sistema puede reemplazar JEV/Laya sin modificar Domain/Application contracts;
* la arquitectura permite evolución futura a multi-capability.

## Related

* ADR-ORCH-001 — LangGraph como runtime reemplazable de orquestación
* ADR-ORCH-006 — Policy Engine & Guardrails
* ADR-ORCH-007 — Execution Contract independiente del runtime
* ADR-ORCH-004 — Agent Registry y descubrimiento de agentes
* ADR-ORCH-013 — LLM Gateway mediante LLMPort

