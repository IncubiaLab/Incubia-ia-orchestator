# Implementación hasta la decisión de modelos

Fecha: 2026-10-01. La base de un mensaje, la conversación local y el adapter HTTP para OpenAI Responses están implementados. El ID de modelo se decidió provisionalmente el 2026-10-02; véase la sección final. No se han hecho llamadas con credenciales.

## Ejecutar

Python 3.12. Desde la raíz, en el entorno con las dependencias de `pyproject.toml` instaladas:

```sh
incubia chat --fake -m "hola"
incubia chat --fake
python -m unittest discover -s tests -v
```

En un checkout sin instalación del paquete puede usarse `PYTHONPATH=src python -m incubia_orchestrator.interfaces.cli.main chat --fake -m hola`.

El REPL acepta `/help`, `/exit` y EOF. Mantiene por defecto diez pares completos de turnos; `--max-turns` y `--max-message-chars` configuran la ventana y el límite de entrada. Fallos y denegaciones no se añaden al historial. El historial se descarta al terminar el proceso.

El proveedor real requiere `OPENAI_API_KEY` y usa `gpt-4o-mini` por defecto; `--model` o `INCUBIA_MODEL` lo sustituyen. `--max-output-tokens`, `--timeout` y `--retries` configuran generación y transporte. El timeout se aplica a cada intento HTTP; todavía no existe deadline total del turno. Los reintentos se aplican solo a timeout, errores de transporte, 429 y errores 5xx seleccionados. Las pruebas usan `httpx.MockTransport` y no necesitan red.

## Decisiones locales y límites

Se añade `ExecutionInput.history: tuple[ConversationTurn, ...]`, una ventana tipada de pares completos cuyo dueño es Application. Es una evolución deliberada de ADR-007: permite transportar contexto del producto al runtime sin convertir GraphState, IDs del proveedor ni objetos de framework en contrato. No cambia el estado Accepted del ADR ni decide la representación futura de especialidad.

La policy local contiene una autoridad fija de deployment, tenant, actor y acción. DENY devuelve un outcome completado de negocio; INDETERMINATE y fallos de policy bloquean la inferencia. REQUIRE_APPROVAL devuelve `APPROVAL_UNSUPPORTED` porque no hay suspensión funcional. `SuspendedExecution` se serializa, y `resume` devuelve `RESUME_UNSUPPORTED`. Esta base no acredita las capacidades completas de ADR-006/007.

El adapter OpenAI usa Responses API con `store=false` y sin tools. El modelo elegido es provisional y falta evaluarlo con API real.

## Selección mínima de especialistas (2026-10-02)

Se eligió `gpt-4o-mini` como valor inicial de los tres perfiles: General, Ventas y Marketing. `--model` o `INCUBIA_MODEL` lo sustituyen para los tres a la vez. El router puro selecciona por términos del mensaje actual, con General como fallback y para empates. La selección es un `Specialty` tipado en el outcome, y la CLI la muestra junto al `request_id`. El grafo ahora ejecuta `START → select_specialty → generate_response → END`. Los ejemplos de validación están en `evals/routing-v1.jsonl`.

Demo local:

```sh
PYTHONPATH=src python -m incubia_orchestrator.interfaces.cli.main chat --fake -m "quiero vender"
PYTHONPATH=src python -m incubia_orchestrator.interfaces.cli.main chat --fake -m "necesito una campaña"
PYTHONPATH=src python -m incubia_orchestrator.interfaces.cli.main chat --fake -m "hola"
```

**Facturación:** la suscripción a ChatGPT/Codex no cubre automáticamente las llamadas de esta aplicación a `api.openai.com`. Para el modo real hace falta una clave de API con facturación o crédito de API propio. La demo `--fake` funciona sin ello. No se realizaron llamadas reales ni mediciones de costo/latencia.
