# Implementación hasta la decisión de modelos

Fecha: 2026-10-01. La base de un mensaje, la conversación local y el adapter HTTP para OpenAI Responses están implementados. Los IDs de modelo siguen pendientes de decisión: `--model` o `INCUBIA_MODEL` es obligatorio al usar el proveedor real. No se han hecho llamadas con credenciales.

## Ejecutar

Python 3.12. Desde la raíz, en el entorno con las dependencias de `pyproject.toml` instaladas:

```sh
incubia chat --fake -m "hola"
incubia chat --fake
python -m unittest discover -s tests -v
```

En un checkout sin instalación del paquete puede usarse `PYTHONPATH=src python -m incubia_orchestrator.interfaces.cli.main chat --fake -m hola`.

El REPL acepta `/help`, `/exit` y EOF. Mantiene por defecto diez pares completos de turnos; `--max-turns` y `--max-message-chars` configuran la ventana y el límite de entrada. Fallos y denegaciones no se añaden al historial. El historial se descarta al terminar el proceso.

El proveedor real requiere `OPENAI_API_KEY` y `--model` o `INCUBIA_MODEL`. `--max-output-tokens`, `--timeout` y `--retries` configuran generación y transporte. El timeout se aplica a cada intento HTTP; todavía no existe deadline total del turno. Los reintentos se aplican solo a timeout, errores de transporte, 429 y errores 5xx seleccionados. Las pruebas usan `httpx.MockTransport` y no necesitan red.

## Decisiones locales y límites

Se añade `ExecutionInput.history: tuple[ConversationTurn, ...]`, una ventana tipada de pares completos cuyo dueño es Application. Es una evolución deliberada de ADR-007: permite transportar contexto del producto al runtime sin convertir GraphState, IDs del proveedor ni objetos de framework en contrato. No cambia el estado Accepted del ADR ni decide la representación futura de especialidad.

La policy local contiene una autoridad fija de deployment, tenant, actor y acción. DENY devuelve un outcome completado de negocio; INDETERMINATE y fallos de policy bloquean la inferencia. REQUIRE_APPROVAL devuelve `APPROVAL_UNSUPPORTED` porque no hay suspensión funcional. `SuspendedExecution` se serializa, y `resume` devuelve `RESUME_UNSUPPORTED`. Esta base no acredita las capacidades completas de ADR-006/007.

El adapter OpenAI usa Responses API con `store=false`, sin tools y sin elegir un modelo por defecto. La siguiente decisión pendiente es seleccionar y evaluar los IDs concretos de modelo; después se podrán probar credenciales reales y continuar con especialidad y routing.
