# Spec 04 — Adapters de runtime y LLM

## LangGraph

Ubicación: `modules/orchestration/adapters/runtime/langgraph/`.

- `adapter.py` implementa `WorkflowRuntimePort` y traduce errores técnicos a errores propios.
- `graph.py` compone el primer graph `START → generate_response → END`.
- `state.py` define `GraphState` exclusivamente para el runtime.
- `mapper.py` transforma `StartExecutionRequest` y `ExecutionOutcome` desde y hacia `GraphState`; también mantiene la frontera para una futura reanudación.
- `nodes/generate_response.py` delega la generación a una capacidad inyectada por el producto.

El adapter mantiene internamente la relación entre `execution_id` y cualquier ID de thread o checkpoint. El checkpoint no es la fuente canónica de conversaciones. No se crea un DSL propio que copie `add_node`/`add_edge` solo para ocultar LangGraph.

## LLM

`modules/orchestration/ports/llm.py` define una solicitud y respuesta propias del producto para generación de texto. El detalle de parámetros, errores, timeout y metadata se finaliza con [HEC-11](https://linear.app/hector-cruz/issue/HEC-11/definir-puertos-de-ia-alineados-con-hexagonal-ddd); no se expone el tipo de respuesta de OpenAI. `modules/orchestration/adapters/llm/openai/` implementa ese puerto y traduce las estructuras del SDK. Bootstrap selecciona el adapter concreto. Un fake LLM satisface el mismo contrato durante pruebas.

## Criterios de aceptación

- `GraphState` no aparece fuera del adapter LangGraph.
- El mapper cubre entrada, salida y errores, sin filtrar IDs técnicos.
- OpenAI se sustituye por un fake sin cambios en Domain/Application.
- El modelo de conversación futuro no persiste `GraphState`.

## Fuentes

[ADR-ORCH-001](https://linear.app/hector-cruz/document/adr-orch-001-langgraph-como-runtime-reemplazable-de-orquestacion-7991e40eb0c2) (aceptado), [ADR-ORCH-013](https://linear.app/hector-cruz/document/adr-orch-013-llm-gateway-mediante-llmport-013214853adf) (propuesto), [ADR-ORCH-019](https://linear.app/hector-cruz/document/adr-orch-019-separacion-entre-conversation-state-y-graphstate-de6cbca510e0) (propuesto).
