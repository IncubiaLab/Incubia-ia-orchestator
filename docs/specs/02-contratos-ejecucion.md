# Spec 02 — Contrato de ejecución

## Objetivo

Exponer el ciclo de vida de una ejecución con tipos serializables propios del producto, independientes del runtime.

## Contratos requeridos

`foundation/contracts/execution.py` define conceptualmente:

- `ExecutionScope`: `deployment_id`, `tenant_id`, `conversation_id`, `actor_id`.
- `ExecutionInput`: `content_type`, `content`, y opcionalmente `locale` y `channel`. El primer slice admite `TEXT`.
- `StartExecutionRequest`: `request_id`, `execution_id`, `scope`, `input`.
- `ResumeExecutionRequest`: `request_id`, el mismo `execution_id`, y un identificador de continuación propio del producto. Su payload detallado queda pendiente del ADR de Human-in-the-Loop.
- `ExecutionOutcome`: unión discriminada de `CompletedExecution`, `SuspendedExecution` y `FailedExecution`, con `request_id`, `execution_id` y estado explícito.
- `CompletedExecution` entrega `output`; `SuspendedExecution` entrega un descriptor con `continuation_id`; `FailedExecution` entrega un error seguro del producto.

`modules/orchestration/ports/workflow_runtime.py` expone `start(StartExecutionRequest) -> ExecutionOutcome` y `resume(ResumeExecutionRequest) -> ExecutionOutcome`. La ejecución inicial usa `start`; `resume` pertenece al contrato desde el inicio, aunque el primer graph aún no suspenda.

## Invariantes

- `conversation_id` identifica la conversación, `execution_id` la ejecución lógica y `request_id` cada invocación. Reanudar preserva `execution_id` y recibe otro `request_id`.
- Los IDs del runtime, checkpoints, `GraphState`, `Command`, objetos de SDK y sesiones de base de datos no cruzan este contrato.
- El scope identifica dónde resolver políticas; no contiene snapshots completos de políticas ni permisos.
- Un rechazo esperado de negocio puede ser un outcome completado; `FailedExecution` representa fallo real de ejecución o infraestructura.
- Los errores de frameworks se traducen a errores propios, seguros para el consumidor.
- No se usa `metadata: dict[str, Any]` como escape para conceptos relevantes.

## Criterios de aceptación

- Los contratos se serializan sin tipos de infraestructura.
- `start` y `resume` no requieren importar LangGraph en Application.
- Los tests cubren los tres outcomes y la estabilidad de IDs al reanudar.

## Fuente

[ADR-ORCH-007](https://linear.app/hector-cruz/document/adr-orch-007-execution-contract-independiente-del-runtime-75eb46c3d112) (aceptado). Este ADR reemplaza los nombres y la firma simplificados del borrador de estructura.
