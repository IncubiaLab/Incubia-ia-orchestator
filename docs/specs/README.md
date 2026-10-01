# Especificaciones del AI Orchestrator MVP

Estas specs convierten la documentación de Linear en criterios verificables para implementar `incubia-ai-orchestrator`. Son diseño; no implican que los componentes ya existan.

## Precedencia y estado

1. ADRs aceptados: [ADR-ORCH-001](https://linear.app/hector-cruz/document/adr-orch-001-langgraph-como-runtime-reemplazable-de-orquestacion-7991e40eb0c2) y [ADR-ORCH-007](https://linear.app/hector-cruz/document/adr-orch-007-execution-contract-independiente-del-runtime-75eb46c3d112).
2. ADRs propuestos: 013, 017, 018, 019 y 020. Son guías de diseño sujetas a ratificación.
3. [Borrador de estructura](https://linear.app/hector-cruz/document/draft-estructura-del-repositorio-incubia-ai-orchestrator-084204cfd1bf), [SAD v1.1](https://linear.app/hector-cruz/document/borrador-sad-agente-orquestador-de-ia-mvp-v11-acd47cd9eb13), [NFRs](https://linear.app/hector-cruz/document/incubia-mvp-nfrs-f626bdd0b279) e issues describen intención y alcance. Cuando difieran de un ADR aceptado, prevalece el ADR.

En particular, el borrador usa `ExecutionRequest`/`ExecutionResult` y `execute()`. ADR-ORCH-007 los sustituye por `StartExecutionRequest`, `ResumeExecutionRequest`, `ExecutionOutcome`, `start()` y `resume()`. Las rutas HTTP del borrador (`/messages` y `/api/v1/messages`) aún requieren una decisión de API; esta especificación adopta `/api/v1/messages` para el primer slice.

## Orden de implementación

| Fase | Specs | Resultado |
| --- | --- | --- |
| 1. Base | [estructura](01-estructura.md), [contratos](02-contratos-ejecucion.md) | Paquetes y tipos propios del producto |
| 2. Primer slice | [orquestación](03-orquestacion.md), [adapters](04-adapters.md), [entrada y bootstrap](05-interfaces-bootstrap.md) | Mensaje HTTP a respuesta mediante LangGraph y LLMPort |
| 3. Verificación | [pruebas](06-pruebas-y-nfr.md) | Límites, contratos y flujo comprobados |
| 4. Evolución | [contextos futuros](07-evolucion-contextos.md) | Capacidades añadidas cuando sus decisiones se ratifiquen |

Cada spec distingue alcance del primer slice y evolución. Las carpetas del primer slice ya están creadas; las carpetas futuras se crean al implementarlas. No se deben añadir módulos vacíos para aparentar avance.
