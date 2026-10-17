# Desarrollo del código

Esta página conecta cada responsabilidad con el archivo que se debe modificar, la razón arquitectónica y la verificación disponible. Complementa la [guía funcional del orquestador](ORQUESTADOR.md).

## Mapa para cambios

| Si cambia… | Revisar primero | Verificar con |
| --- | --- | --- |
| Formato de requests/outcomes o scope | `foundation/contracts/execution.py`, `modules/orchestration/ports/workflow_runtime.py`, mapper LangGraph | `tests/test_boundaries.py`, `tests/test_flow.py` |
| Comandos y límites del chat | `interfaces/cli/main.py`, `application/session.py`, `bootstrap/composition.py` | `tests/test_cli_offline.py`, `tests/test_monthly_limit.py` |
| Selección local de especialidad | `application/router.py`, nodo `select_specialty.py` | `tests/test_routing.py` |
| Resolución por capacidad y agentes | `application/capability_resolver.py`, `selection.py`, `use_cases/handle_inbound.py`, registry in-process | `tests/unit/test_e2_foundation.py` |
| Contexto e historial | `application/context_builder.py`, `conversation/ports/repository.py`, `conversation/application/response_context.py` | `tests/unit/test_response_context.py`, pruebas E2 |
| Policy y generación | nodo `generate_response.py`, `governance/`, puertos y adapters LLM | `tests/test_flow.py`, `tests/test_boundaries.py` |
| Canal Telegram y persistencia | `interfaces/cli/bot.py`, `conversation/adapters/channels/telegram/`, ledger SQLite | `tests/integration/test_telegram_runner.py`, `tests/integration/test_sqlite_ledger.py` |
| HTTP local y ledger PostgreSQL | `interfaces/http/main.py`, `bootstrap/d0.py`, `conversation/adapters/persistence/postgres/` | `tests/unit/test_d0_deployment.py`, smoke E3-D0-L |
| Tools E3 | `orchestration/domain/tools.py`, `application/execute_tool.py`, `adapters/tools/` | `tests/unit/test_tool_discovery.py`, `tests/integration/test_read_tool.py` |

## Método usado para construir el flujo

1. Los contratos de ejecución fijan el vocabulario común (`ExecutionScope`, `StartExecutionRequest`, `ExecutionOutcome`) antes de depender de un framework. Esto implementa [ADR-ORCH-007](../adr/ADR-ORCH-007.md).
2. Los casos de uso coordinan puertos. `HandleMessage` es la fachada local y `HandleInbound` representa la ruta por capacidad/agente. Las reglas de routing y selección se pueden probar sin LangGraph.
3. `bootstrap/` selecciona adapters concretos y les inyecta sus dependencias. La regla de imports y composición procede de [ADR-ORCH-018](../adr/ADR-ORCH-018.md).
4. El adapter LangGraph contiene la mecánica del grafo y el mapping. Sus nodos conectan decisiones de routing, policy y generación; el contrato de Application permanece estable, según [ADR-ORCH-001](../adr/ADR-ORCH-001.md).
5. Los adapters de canal y persistencia administran transporte, deduplicación y entrega. El estado conversacional canónico no se considera un checkpoint de LangGraph; véanse [ADR-ORCH-008](../adr/ADR-ORCH-008-CONVERSATION-STATE-PERSISTENCE.md) y [ADR-ORCH-019](../adr/ADR-ORCH-019.md).

## Documentar un cambio

Actualizar primero el docstring de la frontera pública cuyo comportamiento cambia. Explicar qué recibe, qué devuelve y cómo falla cuando no sea obvio por los tipos. Después actualizar la fila funcional de [ORQUESTADOR.md](ORQUESTADOR.md) y, si cambia la arquitectura o un gate, el ADR o el registro de etapa correspondiente. Mantener ejemplos ejecutables y evitar presentar código de un slice local como funcionalidad productiva. Las decisiones y los gates vigentes están en [PROGRESS E3](../roadmap/etapa-3/PROGRESS.md); las specs describen diseño, no evidencia de implementación.
