# Base de la etapa 1 — Gate 0 técnico

Fecha: 2026-10-01 · Estado inicial: propuesta de implementación. **Gate 0 técnico cerrado para la ruta local permitida el 2026-10-02**, con evidencia en [VERIFICACION.md](VERIFICACION.md).

## Propósito

Demostrar que un mensaje atraviesa los contratos del producto, se ejecuta en LangGraph y vuelve como un outcome propio. La evidencia inicial es una integración local con FakeLLM, sin red ni credenciales.

El **Gate 0 técnico** es el criterio de cierre de los hitos **0 (decisiones)** y **1 (contratos y composición)** del [ROADMAP](ROADMAP.md). No renumera sus hitos ni equivale a completar la etapa 1. REPL, historial y routing especialista se incorporan después.

Prevalecen los ADR [001](../../adr/ADR-ORCH-001.md), [006](../../adr/ADR-ORCH-006.md) y [007](../../adr/ADR-ORCH-007.md), aceptados. Los ADR 013/017/018/019/020 guían esta propuesta conservando su estado Proposed. Implementar la base no ratifica esos ADRs ni acredita todos los criterios del MVP amplio.

## Recorrido mínimo

```text
Entrada local de un mensaje
    → HandleMessage
    → WorkflowRuntimePort.start(StartExecutionRequest)
    → LangGraphRuntimeAdapter
        → mapper de entrada → GraphState
        → START → generate_response → END
                         ↓
                 Policy PEP
                     ↓
             PolicyEnginePort (PDP)
                     ↓ ALLOW
                  LLMPort.generate
                         ↓
                      FakeLLM
        → mapper de salida/error
    → ExecutionOutcome
    → salida local
```

Bootstrap construye el caso de uso y los adapters e inyecta sus dependencias. La interfaz recibe el caso de uso compuesto; solo el adapter LangGraph conoce e invoca el grafo compilado. Antes de una operación protegida, un PEP cercano consulta `PolicyEnginePort` (PDP) y aplica su decisión. El nodo de generación pide evaluación para la acción de inferencia antes de llamar a LLMPort; FakeLLM produce el texto falso solo si la decisión permite la acción. Hay una única configuración de generación y no se seleccionan especialidades.

La frontera distingue tres responsabilidades aceptadas en ADR-006: **Kernel Invariants** son límites estructurales que configuración no puede debilitar; **Policy Engine** decide autorización y restricciones configurables; **Guardrails** evalúan contenido y comportamiento probabilístico, pero no conceden autoridad. Una evaluación `INDETERMINATE` falla cerrada para una operación protegida; la delegación efectiva no puede ampliar los envelopes de producto/operador/tenant/actor. La generación local mínima no implementa guardrails de contenido ni un DSL de políticas.

## Responsabilidades y archivos previstos

Rutas relativas a `src/incubia_orchestrator/`. Crear archivos al implementar su responsabilidad; no se exige el árbol objetivo completo.

| Ubicación | Responsabilidad |
| --- | --- |
| `foundation/contracts/execution.py` | Scope, entrada, requests, outcomes y errores serializables del ADR-007. |
| `modules/orchestration/application/use_cases/handle_message.py` | Construir el request con mensaje, scope e IDs; consumir el puerto. Generador de IDs inyectable. |
| `modules/orchestration/ports/workflow_runtime.py` | `start` y `resume` con tipos propios. |
| `modules/orchestration/ports/llm.py` | Solicitud, respuesta y errores propios de generación; interfaz mínima `generate`. |
| `modules/governance/domain/` y `modules/governance/ports/policy_engine.py` | PolicyQuery/PolicyDecision y PolicyEnginePort neutrales al runtime; autoridad separada de reglas de negocio. |
| `modules/governance/adapters/policy/in_process/` | Evaluación local con revisión identificable; sin motor externo ni DSL. Bootstrap inyecta policy/configuración explícita. |
| PEP en el flujo de generación | Consultar y hacer cumplir policy junto a la invocación de LLM; nunca confiar en que el nodo o LLM otorguen permisos. |
| `modules/orchestration/adapters/runtime/langgraph/adapter.py` | Implementar el puerto; encapsular invocación y errores técnicos. |
| `modules/orchestration/adapters/runtime/langgraph/graph.py` | Construir `START → generate_response → END`. |
| `modules/orchestration/adapters/runtime/langgraph/state.py` | Estado técnico privado de una ejecución. |
| `modules/orchestration/adapters/runtime/langgraph/mapper.py` | Traducir request, estado y outcome sin filtrar tipos o IDs del runtime. |
| `modules/orchestration/adapters/runtime/langgraph/nodes/generate_response.py` | Delegar una generación al puerto inyectado y actualizar el estado. |
| `modules/orchestration/adapters/llm/fake.py` | Respuesta determinista para demo y fallos controlables en tests. |
| `bootstrap/` | Validar configuración local, construir implementaciones e inyectarlas. |
| `interfaces/cli/main.py` | Entrada de un mensaje y presentación del outcome; sin imports de LangGraph ni SDKs. |

Demostración propuesta: `incubia chat --fake -m "hola"`, un solo turno sin REPL. La interfaz llama a un punto de composición de bootstrap sin construir adapters. El comando se instala mediante pyproject.toml y tiene instrucciones reproducibles.

## Contratos y decisiones mínimas

| Tema | Propuesta | Estado / límite |
| --- | --- | --- |
| Entrada | `StartExecutionRequest(request_id, execution_id, scope, input)`; ExecutionInput de texto. | ADR-007. Sin historial ni especialidad en este gate. |
| Scope | deployment_id, tenant_id, conversation_id, actor_id; bootstrap configura scope local sintético. | No implementa autenticación ni aislamiento multi-tenant. |
| Salida | ExecutionOutcome: completed, suspended o failed; output de texto tipado y error propio seguro. | ADR-007; concretar serialización sin objetos de framework. |
| Lifecycle inicial | Puerto con start y resume; grafo produce completed o failed. | Recorte propuesto: resume devuelve failed con código propio RESUME_UNSUPPORTED; no emite suspended. Suspensión/reanudación funcional pendiente. |
| Suspensión | Conservar variante y continuation_id propio previstos en ADR-007. | Detalle del descriptor pendiente de ADR-012; no inventar payload libre ni simular cumplimiento funcional. |
| Gobierno | PolicyQuery (principal/acción/recurso/contexto); PolicyDecision con efecto, motivo, obligaciones e identificación/revisión de policy. Efectos ALLOW, DENY, REQUIRE_APPROVAL e INDETERMINATE. | ADR-006 aceptado. `PolicyEnginePort` neutral al runtime y adapter in-process; una regla local versionada basta para este recorrido. No adopta OPA/Cedar/OpenFGA ni un DSL. Indeterminate falla cerrada. |
| REQUIRE_APPROVAL | Semántica de policy se traduce a SuspendedExecution; LangGraph solo implementa pausa/reanudación. Reevaluar policy al reanudar. | Exigencia de ADR-006; no declarar esta capacidad completa si el corte inicial omite suspensión/resume funcional. |
| Guardrails | Frontera aparte de autorización; nunca elevan permisos. | No se incorporan análisis de prompt injection, PII ni filtros probabilísticos al gate de FakeLLM. |
| Generación | Request propio con instrucciones, texto y límites; respuesta propia con texto. Proveedor/modelo en adapter/bootstrap. | LLMPort propuesto (ADR-013). Uso de tokens opcional y tipado al incorporar proveedor real; fake no acredita costo real. |
| Concurrencia | Firmas síncronas propuestas para este flujo local. | ADR-007 no lo impone. Revisar antes del proveedor real según cancelación y deadlines. |
| Estado | GraphState nuevo por ejecución, sin checkpointer. | Historial en Application, hito 2. |

Registrar decisiones locales y límites en el hito 0. El PEP no se omite solo porque el proveedor actual sea FakeLLM. El flujo permite generación únicamente tras ALLOW; DENY no invoca el modelo e INDETERMINATE no se convierte en ALLOW. El mecanismo que mapea DENY a un outcome seguro del producto debe respetar que un resultado de policy no es necesariamente un fallo técnico. No se exige ratificar globalmente todos los ADR Proposed. `resume` no soportado limita el cumplimiento de ADR-007 y no acredita la exigencia de ADR-006 de reevaluar policy después de una suspensión.

## Orden de construcción

1. Cerrar tipos de ejecución, generación, errores y serialización; registrar recorte de lifecycle. Historial y especialidades se deciden después.
2. Crear paquete y puertos; probar HandleMessage con runtime falso para verificar Application sin LangGraph.
3. Implementar FakeLLM y probar generación/errores sin grafo.
4. Implementar estado, mappers, nodo, grafo y adapter; comprobar start con LangGraph y FakeLLM.
5. Componer desde bootstrap y exponer un mensaje. Fijar versiones compatibles en archivo de bloqueo.
6. Ejecutar las comprobaciones siguientes y guardar instrucciones/resultados reproducibles.

## Evidencias para cerrar el gate

Las evidencias siguientes se comprobaron en la implementación local y en la suite sin red; el resultado y sus límites están en [VERIFICACION.md](VERIFICACION.md).

- [x] El comando instalado produce CompletedExecution pasando por HandleMessage, puerto, LangGraph y FakeLLM.
- [x] La generación exitosa llama una vez al LLM con la entrada esperada y devuelve su texto mediante el mapper.
- [x] Fallos controlados del LLM y del runtime producen FailedExecution con IDs conservados, sin excepciones ni objetos internos expuestos.
- [x] La PolicyQuery/Decision y PolicyEnginePort son contratos del producto; ALLOW permite una generación y DENY/INDETERMINATE no llaman LLMPort. El PEP está cerca de la inferencia y registra revision/decision sin texto del usuario.
- [x] La autoridad local se configura explícitamente y no se amplía por tenant, actor, nodo ni sugerencia de LLM; business rules y guardrails no se mezclan en el Policy Engine.
- [x] Requests y outcomes admiten ida y vuelta JSON preservando variantes e IDs; suspended se prueba como representación, sin afirmar pausa/reanudación funcional.
- [x] Resume tiene comportamiento explícito, probado y documentado para este runtime sin suspensión.
- [x] Application funciona con runtime falso; la integración usa el mismo caso de uso con LangGraph.
- [x] Tests de arquitectura impiden infraestructura en contratos, puertos, Domain y Application; CLI no importa LangGraph ni SDK del proveedor. Se consideran imports transitivos locales que evadan la frontera.
- [x] GraphState y grafo compilado permanecen dentro del adapter; conversiones al contrato público centralizadas en mappers.
- [x] Suite sin credenciales, con red bloqueada y comprobación del bloqueo, también en subprocesos si los tests los usan.
- [x] Guía de ejecución, Python y dependencias bloqueadas; instalación y comando de un turno reproducibles.

Cerrar el gate acredita el recorrido permitido inicial y la frontera básica de enforcement. Quedan pendientes el lifecycle REQUIRE_APPROVAL/SuspendedExecution con reevaluación tras resume, guardrails de contenido, policies configurables completas, identidad multi-tenant y capacidades del adapter OpenAI. No se puede presentar la verificación de esta ruta básica como validación completa de ADR-006.

## Evolución y estado actual

| Momento | Incorporación |
| --- | --- |
| Hito 2 | REPL, historial, errores, logs y adapter real; resolver primero transporte del contexto. |
| Hito 3 | Router puro, perfiles, especialidad visible y eval; resolver primero representación tipada de selección. |
| Hito 4 | Suite completa, medición real de latencia/costo y guía final. |

El experimento `graph.py` se sustituyó por el adapter de LangGraph. La base se verificó primero con un nodo de generación; el grafo actual añade selección de especialidad antes de generar. El cierre del gate se limita a la ruta local sin suspensión funcional.
