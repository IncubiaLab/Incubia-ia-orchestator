# Orquestador: funciones, uso y construcción

Esta página compara la función visible con el código que la realiza. Describe el estado del repositorio al 15 de octubre de 2026. Para ejecutar los comandos se necesita el entorno del [README principal](../../README.md); las pruebas y los gates de E3 se registran en [PROGRESS](../roadmap/etapa-3/PROGRESS.md).

## Qué hace

El orquestador recibe un mensaje dentro de un contexto de ejecución, selecciona una especialidad o capacidad, evalúa la política antes de generar y entrega un resultado tipado. La conversación, el runtime, la identidad y los proveedores están separados por contratos. No todas las entradas usan todavía la misma estrategia de selección ni los mismos almacenes.

| Función y uso | Construcción en código | Estado |
| --- | --- | --- |
| Chat de terminal con General, Ventas y Marketing | `interfaces/cli/main.py` → `ConversationSession` → `HandleMessage` → `WorkflowRuntimePort` → `LangGraphRuntimeAdapter` | Disponible localmente; routing por términos. |
| Generación determinista sin API | `bootstrap/composition.py:compose(fake=True)` inyecta `FakeLLM` | Disponible para desarrollo y pruebas. |
| Generación con OpenAI | `compose(fake=False)` inyecta `OpenAILLM` y `MonthlyCallLimiter` | Disponible con clave y cupo; límites en README principal. |
| Chat Telegram por polling | `interfaces/cli/bot.py` → `TelegramRunner` → ledger SQLite → `compose_scoped` | Implementado; piloto y evaluación E2 pendientes de cierre. |
| Entrada HTTP local durable | `interfaces/http/main.py` → `bootstrap/d0.py` → ledger PostgreSQL | Baseline E3-D0-L acreditado en loopback; no es API pública general. |
| Resolución por capacidad y agente | `HandleInbound` usa `CapabilityResolver`, `AgentDiscoveryPort`, `select` y `ContextBuilder` | Implementación E2 parcial; no sustituye el router local de la CLI. |
| Identidad, tools y auditoría E3 | `identity_tenant/`, `orchestration/*/tools/`, `audit/` | Slices locales; gates H2/H3 abiertos. |

## Uso de las entradas

### CLI local

```sh
uv run --project . --extra test incubia chat --fake -m "quiero vender"
uv run --project . --extra test incubia chat --fake
```

El segundo comando abre el chat interactivo; acepta `/help` y `/exit`. Cada proceso crea un scope local y una sesión nueva. `ConversationSession` valida texto y tamaño, mantiene pares usuario/asistente hasta el límite configurado y añade al historial solo respuestas completadas de tipo `message`. El router normaliza acentos y busca términos de ventas/marketing; si encuentra ambos, usa General. Este es un baseline determinista, no clasificación semántica general.

Sin `--fake`, el comando usa el proveedor real. La CLI restringe historial a dos pares, mensaje a 500 caracteres, salida a 128 tokens y reintentos a cero. `INCUBIA_MODEL`, `OPENAI_API_KEY`, `INCUBIA_BUDGET_FILE` e `INCUBIA_LOG_FILE` permiten configurar modelo, clave, contador local y log. El log registra metadatos de operación, no el contenido del chat. Detalles y preparación: [README principal](../../README.md).

### Telegram

```sh
uv run --project . --extra test incubia-bot discover
uv run --project . --extra test incubia-bot run --fake --once --bindings config/e2/bindings.yaml
uv run --project . --extra test incubia-bot inspect
```

`discover` consulta identificadores de chats privados pendientes para configurar bindings. `run` valida el bot y los bindings, compone generación con scope confiable, recupera el ledger y procesa ciclos de polling; `--once` termina tras un ciclo. `inspect` muestra eventos y entregas que requieren revisión. También existe `--multi-session`, que crea un binding aislado por chat privado nuevo. El ledger SQLite conserva inbox, outbox, historial y estado de entrega. La [guía Telegram](../roadmap/etapa-2/TELEGRAM.md) explica operación y recuperación.

### HTTP E3-D0-L

El servidor de `interfaces/http/main.py` expone `GET /healthz`, `GET /readyz` y `POST /v1/executions` para el despliegue local de referencia. El payload de ejecución acepta **solo** `message` y `conversation_id`; la identidad no se toma del cuerpo HTTP. La composición y la persistencia están en `bootstrap/d0.py` y el adapter PostgreSQL. Su uso reproducible está en el [runbook E3](../roadmap/etapa-3/RUNBOOK.md). No se debe inferir que este endpoint ofrece la misma integración, proveedor o alcance del runner Telegram.

## Cómo se procesa un mensaje local

```text
CLI → ConversationSession → HandleMessage → WorkflowRuntimePort
                                            ↓
                              LangGraphRuntimeAdapter
                                            ↓
                          select_specialty → generate_response
                                                   ↓
                                         PolicyEngine → LLMPort
```

1. `compose` decide proveedor y límites; construye el motor de políticas y el grafo.
2. `HandleMessage` crea `request_id` y `execution_id` separados, además de `StartExecutionRequest` con texto, historial y `ExecutionScope`.
3. El adapter mapea el request a `GraphState`, invoca el grafo y convierte su estado en `CompletedExecution` o `FailedExecution`.
4. `select_specialty` ejecuta el router local. `generate_response` evalúa `llm.generate` para el actor antes de invocar el puerto LLM. Una denegación produce una respuesta `policy_denied`; aprobación requerida o policy indeterminada generan errores controlados.
5. `ConversationSession` actualiza el historial solo si hubo una respuesta normal completada. La CLI imprime la etiqueta de especialidad y guarda metadatos de la ejecución.

`ExecutionOutcome` también declara `SuspendedExecution`, pero el adapter actual devuelve `RESUME_UNSUPPORTED` al llamar `resume()`. Una excepción no controlada del grafo se traduce a `RUNTIME_ERROR`; por ello los consumidores no dependen de excepciones de LangGraph.

## Contratos y decisiones

`foundation/contracts/execution.py` define scope, input, requests y outcomes serializables. `modules/orchestration/ports/workflow_runtime.py` define la frontera del runtime; los tipos `GraphState` y `StateGraph` permanecen en el adapter. La razón de esta separación está en [ADR-ORCH-001](https://linear.app/hector-cruz/document/adr-orch-001-langgraph-como-runtime-reemplazable-de-orquestacion-7991e40eb0c2) y la regla de ensamblaje en [ADR-ORCH-018](https://linear.app/hector-cruz/document/adr-orch-018-regla-de-dependencias-y-composition-root-51a80e712bf0).

La ruta de `HandleInbound` resuelve comandos explícitos (`/general`, `/ventas`, `/marketing`) o consulta `DecisionModelPort`, filtra capacidades elegibles, descubre descriptores, selecciona por prioridad/id/versión y construye contexto con hechos e historial acotados por presupuesto. Si no hay ruta o agente elegible devuelve `None`. La implementación actual pasa el historial construido al runtime; otros campos del contexto se conservan en `SpecialtyContext`, pero no se incorporan todavía al `ExecutionInput` de este caso de uso.
