# Spec 03 — Caso de uso y workflow inicial

## Objetivo

Procesar un mensaje de texto de extremo a extremo mediante un caso de uso de Application y un runtime intercambiable.

## Primer slice

1. El adapter HTTP normaliza el mensaje y construye un comando del producto.
2. `HandleMessage`, en `modules/orchestration/application/use_cases/`, crea `StartExecutionRequest` con IDs y scope válidos.
3. El caso de uso invoca `WorkflowRuntimePort.start()`.
4. El adapter LangGraph ejecuta `START → generate_response → END`.
5. El nodo `generate_response` coordina la generación mediante `LLMPort`; no incorpora políticas de tenant ni reglas de negocio.
6. El adapter mapea el estado técnico a `ExecutionOutcome`; Application devuelve el resultado al adapter HTTP.

El primer slice demuestra una respuesta real por el puerto. No incorpora todavía routing complejo, RAG, registries, tool execution, handoffs ni multiagente. [HEC-12](https://linear.app/hector-cruz/issue/HEC-12/implementar-ai-orchestrator-del-mvp) describe el flujo objetivo más amplio; sus partes de identidad, retrieval, tools y audit se implementan en fases posteriores según sus contratos y ADRs.

## Propiedad de decisiones

- Producto/Application: identidad y scope efectivos, selección de capacidades, políticas, autorización, significado de éxito/fallo y escalamiento.
- LangGraph adapter: topología del graph, estado técnico, recorrido, pausas, checkpoints y retries técnicos.
- Product/kernel invariants tienen precedencia sobre políticas de deployment, tenant, agentes y sugerencias del LLM.
- Las reglas del operador no presuponen que Incubia administre todos los deployments.

## Criterios de aceptación

- `HandleMessage` solo depende de contratos y puertos del producto.
- El graph mínimo responde a un texto mediante un fake LLM en pruebas y mediante el adapter configurado en integración.
- Los nodos no toman decisiones de autorización ni contienen reglas comerciales.
- Un fallo técnico se convierte en `FailedExecution` seguro; un outcome de negocio esperado conserva su semántica.

## Fuentes

[ADR-ORCH-001](https://linear.app/hector-cruz/document/adr-orch-001-langgraph-como-runtime-reemplazable-de-orquestacion-7991e40eb0c2) (aceptado), [borrador de estructura](https://linear.app/hector-cruz/document/draft-estructura-del-repositorio-incubia-ai-orchestrator-084204cfd1bf), [HEC-12](https://linear.app/hector-cruz/issue/HEC-12/implementar-ai-orchestrator-del-mvp).
