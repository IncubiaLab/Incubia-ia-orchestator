# Spec 05 — Entrada HTTP y composición

## HTTP

La interfaz de entrada vive en `src/incubia_orchestrator/interfaces/http/`. Para el primer slice, `POST /api/v1/messages` acepta `message` de texto, valida la entrada, resuelve el scope necesario y llama a `HandleMessage`. Los schemas HTTP pertenecen a la interfaz; los contratos internos no dependen de FastAPI ni Pydantic.

El controller traduce `CompletedExecution`, `SuspendedExecution` y `FailedExecution` a respuestas HTTP definidas por la interfaz. Los códigos y el esquema final de error se deben cerrar antes de exponer el endpoint públicamente. Nunca devuelve IDs de thread, checkpoints ni errores crudos de proveedores.

La estructura mínima creada contiene `interfaces/http/routes/`; el borrador objetivo propone `interfaces/http/v1/routes/` y `schemas/`. Antes de implementar HTTP se elige una de ellas y se conserva una sola ruta de código. Esta spec fija la URL pública v1, no obliga a duplicar carpetas.

## Bootstrap

`bootstrap/settings.py` carga configuración y secretos desde el entorno; `container.py` construye el OpenAI adapter, LangGraph adapter y caso de uso; `app.py` expone la aplicación. Solo bootstrap conoce implementaciones concretas. Credenciales nunca se incluyen en código, logs ni respuestas.

## Criterios de aceptación

- Una llamada válida devuelve la salida del `ExecutionOutcome` sin tipos internos del runtime.
- Entrada inválida se rechaza antes de invocar el caso de uso.
- El scope incluye deployment, tenant, conversation y actor; ninguna entrada arbitraria del cliente se considera identidad confiable sin resolución/autenticación.
- Domain/Application no importan FastAPI ni OpenAI.
- Cambiar la implementación de `LLMPort` solo requiere cambios de composición/configuración.

## Fuentes

[Borrador de estructura](https://linear.app/hector-cruz/document/draft-estructura-del-repositorio-incubia-ai-orchestrator-084204cfd1bf), [ADR-ORCH-018](https://linear.app/hector-cruz/document/adr-orch-018-regla-de-dependencias-y-composition-root-51a80e712bf0) (propuesto), [ADR-ORCH-007](https://linear.app/hector-cruz/document/adr-orch-007-execution-contract-independiente-del-runtime-75eb46c3d112) (aceptado), [NFRs](https://linear.app/hector-cruz/document/incubia-mvp-nfrs-f626bdd0b279).
