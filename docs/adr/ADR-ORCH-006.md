<!-- Fuente: https://linear.app/hector-cruz/document/adr-orch-006-policy-engine-and-guardrails-78ffd068145a
Sincronizado desde Linear el 2026-10-01. El estado se conserva tal como figura en el documento de origen. -->

# ADR-ORCH-006 — Policy Engine & Guardrails

**Status:** Accepted
**Scope:** `incubia-ai-orchestrator`

## Context

El Orchestrator debe controlar autorización, aislamiento multi-tenant, acceso a datos, uso de tools/modelos y human approval sin delegar autoridad al runtime ni al LLM.

Las decisiones previas establecen que:

* `ADR-ORCH-001` separa la semántica del producto de la mecánica de ejecución de LangGraph;
* `ADR-ORCH-007` define contratos de ejecución runtime-neutral que transportan scope e identidad, pero no policies completas;
* el producto debe ser adaptable a distintos operadores, deployments y tenants sin asumir que Incubia será siempre la autoridad operativa final.

Por ello se requiere una arquitectura de governance que distinga claramente invariantes estructurales, políticas configurables y guardrails de contenido/IA.

## Decision

Se adopta una arquitectura de governance con tres mecanismos separados:

```text
Kernel Invariants
      ↓
Policy Engine
      ↓
Guardrails
```

### 1. Kernel Invariants

Son restricciones estructurales no configurables necesarias para preservar seguridad y consistencia del producto.

Ejemplos:

* aislamiento estricto entre tenants;
* una policy de tenant no puede ampliar autoridad por encima del operador;
* un LLM o agente nunca puede concederse permisos;
* una operación protegida no puede omitir el Policy Enforcement Point;
* Domain/Application no dependen del runtime;
* los invariantes del producto no pueden ser modificados por Operator o Tenant Policy.

Los Kernel Invariants no se almacenarán como simple configuración editable por tenants u operadores.

### 2. Policy Engine

El Policy Engine gobierna autorización y restricciones configurables de ejecución.

Se adopta el patrón Policy Decision Point / Policy Enforcement Point (PDP/PEP):

```text
PEP ─────► PDP / PolicyEnginePort
 │             │
 │             ▼
 │       PolicyDecision
 │             │
 ◄─────────────┘
 │
 ▼
enforce
```

* **PDP:** evalúa la política y produce una decisión.
* **PEP:** aplica la decisión cerca de la operación protegida.

El Policy Engine será accesible mediante un puerto propio del producto:

```python
class PolicyEnginePort(Protocol):
    async def evaluate(self, query: PolicyQuery) -> PolicyDecision:
        ...
```

No se adopta en este ADR una tecnología concreta como OPA, Cedar u OpenFGA.

### 3. Guardrails

Los Guardrails controlan contenido y comportamiento probabilístico, no autoridad.

Ejemplos:

* prompt injection;
* sensitive-data leakage;
* unsafe output;
* PII exposure;
* validación de structured output;
* restricciones de contenido específicas del tenant.

Un guardrail probabilístico puede bloquear, marcar, escalar o requerir revisión, pero **nunca aumentar permisos ni conceder autoridad**.

## Authority Envelope

La autoridad se modela como envelopes anidados, no como simples overrides:

```text
┌───────────────────────────────┐
│ PRODUCT AUTHORITY ENVELOPE    │
│                               │
│ ┌───────────────────────────┐ │
│ │ OPERATOR ENVELOPE         │ │
│ │                           │ │
│ │ ┌───────────────────────┐ │ │
│ │ │ TENANT ENVELOPE       │ │ │
│ │ │                       │ │ │
│ │ │ ┌───────────────────┐ │ │ │
│ │ │ │ EFFECTIVE ACTOR   │ │ │ │
│ │ │ │ AUTHORITY         │ │ │ │
│ │ │ └───────────────────┘ │ │ │
│ │ └───────────────────────┘ │ │
│ └───────────────────────────┘ │
└───────────────────────────────┘
```

Un nivel inferior puede restringir o seleccionar dentro de lo permitido, pero no ampliar autoridad más allá del nivel superior.

### Delegación explícita

El operador podrá delegar namespaces concretos al tenant, por ejemplo:

```text
Tenant may configure:
- enabled_capabilities
- allowed_models
- support_hours
- sales_limits
```

La delegación debe ser explícita; no se asume por defecto.

## PolicyQuery

El contrato será runtime-neutral y conceptualmente seguirá:

```text
Principal
Action
Resource
Context
```

Ejemplo conceptual:

```text
principal:
    user:123

action:
    crm.customer.update

resource:
    customer:991

scope:
    deployment:abc
    tenant:dealer-42

context:
    execution_id
    channel
    agent
    risk
```

Los tipos concretos se definirán en el módulo de governance y no dependerán de OPA, Cedar, OpenFGA, LangGraph u otros frameworks.

## Principal, agent y delegación

El principal efectivo puede incluir distintos actores:

```text
initiator
executor
on_behalf_of
```

Ejemplo:

```text
initiator: user:123
executor: sales-agent
on_behalf_of: user:123
```

Regla estructural:

> La delegación nunca aumenta autoridad.

Conceptualmente:

```text
effective authority
=
actor authority
∩ agent authority
∩ tenant policy
∩ operator policy
∩ product constraints
```

## PolicyDecision

No se utilizará un booleano simple.

Los efectos iniciales serán:

```text
ALLOW
DENY
REQUIRE_APPROVAL
INDETERMINATE
```

`INDETERMINATE` no equivale a `ALLOW`.

Para operaciones protegidas, errores o imposibilidad de evaluar la policy aplican **fail-closed** mediante `DENY` o escalamiento controlado.

## Obligations

Una policy podrá permitir una operación con obligaciones adicionales:

```text
effect: ALLOW
obligations:
- audit
- redact_sensitive_data
- max_rows: 100
- model: local-only
```

Esto evita introducir múltiples efectos especializados como `ALLOW_WITH_X`.

`PolicyDecision` deberá poder transportar conceptualmente:

```text
decision_id
effect
reason_codes
obligations
matched_policies
policy_revision
```

La revisión/versionado de policy permitirá reproducir y auditar por qué una decisión fue tomada en un momento concreto.

## Enforcement distribuido

No existirá un único `check_policy()` al inicio del workflow.

Se ubicarán PEPs cerca de operaciones protegidas, por ejemplo:

* capability selection/filtering;
* retrieval y acceso a datasources;
* acceso a recursos específicos;
* selección de modelos externos/locales;
* tool execution;
* mutation tools;
* handoffs;
* exports;
* resume de ejecuciones suspendidas.

## Re-evaluación

Las policies no se consideran válidas para siempre durante una ejecución larga.

Las operaciones protegidas deberán reevaluarse en el momento de enforcement, especialmente después de `resume`.

Ejemplo:

```text
09:00 request
   ↓
SUSPENDED

11:00 permission revoked

12:00 approval received
   ↓
RESUME
   ↓
POLICY RE-EVALUATION
   ↓
DENY
```

Una aprobación humana no restaura permisos que ya no están vigentes.

## Integración con ORCH-007

`REQUIRE_APPROVAL` se representa semánticamente mediante el lifecycle de ejecución definido en `ADR-ORCH-007`:

```text
PolicyDecision: REQUIRE_APPROVAL
            ↓
SuspendedExecution
            ↓
WorkflowRuntimePort
            ↓
LangGraph interrupt
```

Policy decide que se requiere aprobación; LangGraph implementa la mecánica de pausa/reanudación.

## Business Rules vs Policy

El Policy Engine no se convertirá en un God Service.

Separación:

```text
Business Rules
      ↓
Domain / Application

Authorization / Execution Constraints
      ↓
Policy Layer

Runtime mechanics
      ↓
LangGraph
```

Reglas como cálculo de precios, lógica comercial o transformación de datos permanecen en Domain/Application salvo que su naturaleza sea explícitamente de autorización/restricción.

## Policies as Data

Operator/Tenant policies serán datos versionados y no lógica hardcodeada por tenant.

Evitar:

```python
if tenant == "acme":
    ...
```

Preferir conceptualmente:

```text
Policy Store
├── deployment/operator-policy-vN
└── tenant/<tenant-id>/policy-vN
```

La incorporación de un cliente deberá depender principalmente de configuración, capabilities, tools, policies y knowledge, no de forks de código.

## MVP Implementation Strategy

Para el MVP se utilizará:

```text
PolicyEnginePort
      ▲
      │
InProcessPolicyAdapter
```

La implementación será in-process para minimizar latencia y complejidad operativa.

No se creará un DSL propio de policies en esta etapa.

Tecnologías externas como OPA, Cedar, OpenFGA u otros motores podrán integrarse posteriormente mediante adapters si aparecen necesidades reales de operación, escala o expresividad.

## Module Placement

Se propone un bounded context/módulo transversal de governance:

```text
modules/
└── governance/
    ├── domain/
    │   ├── policy_query.py
    │   ├── policy_decision.py
    │   ├── obligation.py
    │   └── guardrail_result.py
    ├── application/
    │   ├── evaluate_policy.py
    │   └── evaluate_guardrail.py
    ├── ports/
    │   ├── policy_engine.py
    │   ├── policy_repository.py
    │   └── guardrail.py
    └── adapters/
        ├── policy/
        │   └── in_process/
        └── guardrails/
```

La ubicación definitiva deberá permanecer alineada con `ADR-ORCH-017`.

## Consequences

### Positive

* autoridad y runtime permanecen desacoplados;
* soporta distintos operadores y tenants;
* evita que agents/LLMs aumenten sus propios permisos;
* facilita auditoría reproducible mediante policy revisions;
* permite extraer o sustituir el motor de políticas sin afectar Domain/Application;
* enforcement cercano a recursos reduce bypasses accidentales;
* HITL se integra naturalmente con el Execution Contract;
* un deployment puede restringir o delegar configuración sin crear forks del producto.

### Negative / Cost

* aumenta el número de PEPs que deben mantenerse correctamente;
* requiere versionado y carga consistente de policies;
* obliga a distinguir cuidadosamente business rules de authorization policies;
* la reevaluación incrementa ligeramente el coste de operaciones protegidas;
* habrá que diseñar contratos de principal/resource/context suficientemente expresivos sin convertirlos en estructuras genéricas sin semántica.

## Alternatives considered

### Un único check de permisos al inicio

Rechazado porque no protege operaciones sensibles posteriores ni workflows largos/resumibles.

### LangGraph como autoridad de policy

Rechazado porque el runtime no debe poseer semántica de autorización.

### LLM como policy decision maker

Rechazado porque una decisión probabilística no debe conceder autoridad.

### Todo configurable por tenant

Rechazado porque permitiría vulnerar invariantes y límites del operador/producto.

### OPA/Cedar/OpenFGA como dependencia obligatoria del MVP

No adoptado. El contrato se mantendrá technology-neutral y la implementación inicial será in-process.

## Validation Criteria

La decisión se considera correctamente implementada cuando:

* existe `PolicyEnginePort`;
* existen `PolicyQuery` y `PolicyDecision` propios del producto;
* se distinguen Kernel Invariants, Policy Engine y Guardrails;
* existen efectos `ALLOW`, `DENY`, `REQUIRE_APPROVAL` e `INDETERMINATE`;
* operaciones protegidas aplican fail-closed;
* ningún LLM/agent puede conceder permisos;
* la delegación no aumenta autoridad;
* Operator/Tenant policies son datos versionados;
* los PEPs están situados cerca de operaciones protegidas;
* las policies se reevalúan tras `resume` cuando corresponda;
* `REQUIRE_APPROVAL` puede producir `SuspendedExecution` sin exponer primitivas LangGraph;
* el Policy Engine no contiene business rules generales del dominio;
* la implementación inicial puede ejecutarse in-process mediante un adapter reemplazable.

## Related

* ADR-ORCH-001 — LangGraph como runtime reemplazable de orquestación
* ADR-ORCH-007 — Execution Contract independiente del runtime
* ADR-ORCH-012 — Human-in-the-Loop
* ADR-ORCH-017 — Estructura module-first y bounded-context-first
* SAD v1.1 — Incubia AI Orchestrator
