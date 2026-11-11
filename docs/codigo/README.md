# Guía del código

Documentos principales: [funciones, usos y construcción del orquestador](ORQUESTADOR.md) y [guía de desarrollo del código](DESARROLLO.md).

Esta guía describe **lo implementado** en `src/incubia_orchestrator/`. Las [specs](../specs/README.md) y el [roadmap E3](../roadmap/etapa-3/ROADMAP.md) incluyen también trabajo futuro; no deben leerse como inventario del runtime actual. Para decisiones arquitectónicas y estado de aprobación, consultar los [ADR locales](../adr/README.md) y sus enlaces a Linear.

## Cómo leer el repositorio

| Lugar | Responsabilidad actual |
| --- | --- |
| `foundation/contracts/` | Tipos de request, scope y outcome compartidos entre módulos. |
| `modules/*/domain/` | Modelos y reglas propios de cada contexto. |
| `modules/*/application/` | Casos de uso y coordinación de puertos. |
| `modules/*/ports/` | Contratos requeridos por los casos de uso. |
| `modules/*/adapters/` | Implementaciones concretas para proveedor, persistencia, canal y runtime. |
| `bootstrap/` | Selección y ensamblaje de implementaciones. |
| `interfaces/` | Entradas CLI y HTTP. |

La dirección de dependencias y el ensamblaje siguen [ADR-ORCH-018](https://linear.app/hector-cruz/document/adr-orch-018-regla-de-dependencias-y-composition-root-51a80e712bf0). `WorkflowRuntimePort` separa el caso de uso de LangGraph, conforme a [ADR-ORCH-001](https://linear.app/hector-cruz/document/adr-orch-001-langgraph-como-runtime-reemplazable-de-orquestacion-7991e40eb0c2).

## Recorrido del chatbot local

1. `interfaces/cli/main.py` recibe el mensaje y llama al objeto construido por `bootstrap/composition.py:compose`.
2. `HandleMessage` crea `request_id` y `execution_id`, conserva el `ExecutionScope` y empaqueta texto e historial en `StartExecutionRequest`.
3. `WorkflowRuntimePort.start` es la frontera de Application. `LangGraphRuntimeAdapter` convierte el request a `GraphState`, invoca el grafo y mapea el resultado a `ExecutionOutcome`. Ante una excepción del grafo, devuelve `RUNTIME_ERROR`.
4. El grafo local ejecuta `select_specialty` y después `generate_response`. El segundo nodo consulta la policy antes de llamar a `LLMPort`; denegaciones, aprobación no soportada y errores del proveedor se convierten en resultados controlados.
5. `compose(fake=True)` usa `FakeLLM`. En modo real crea `OpenAILLM` con presupuesto mensual y límites de salida; los detalles operativos están en el [README principal](../../README.md).

La ruta de entrada multicanal usa `HandleInbound`: resuelve capacidad, busca un agente elegible, construye contexto e inicia el runtime con su perfil. Telegram usa además `compose_scoped` para componer la policy por `deployment_id`, `tenant_id` y `actor_id`. Ver [etapa 2](../roadmap/etapa-2/IMPLEMENTACION.md) para la evolución del canal y [ADR-ORCH-008](../adr/ADR-ORCH-008-CONVERSATION-STATE-PERSISTENCE.md) para el estado conversacional.

## Alcance y estado

`resume()` devuelve `RESUME_UNSUPPORTED` en el adapter LangGraph actual. Las carpetas de tools, auditoría e identidad contienen trabajo E3 en curso; su alcance y gates se registran en [PLAN-E3](../roadmap/etapa-3/PLAN-E3.md) y [PROGRESS](../roadmap/etapa-3/PROGRESS.md). La existencia de un contrato o adapter no implica habilitación productiva.

## Criterio de documentación

Los docstrings explican la responsabilidad observable, parámetros o resultados que no se deducen de la firma, y condiciones de fallo relevantes. No repiten línea por línea el algoritmo. Las razones de diseño y la historia de implementación viven aquí, en los ADR y en los registros de etapa; al cambiar un comportamiento, actualizar la guía y el docstring de su frontera pública. Para ubicar la evidencia, buscar el identificador de tarea del roadmap en `docs/roadmap/` y las pruebas bajo `tests/`.
