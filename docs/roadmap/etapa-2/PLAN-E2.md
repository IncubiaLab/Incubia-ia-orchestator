# Plan ejecutable — etapa 2

> Para agentes: ejecutar con superpowers:executing-plans o superpowers:subagent-driven-development, una tarea a la vez y con TDD: prueba que falla → implementación mínima → prueba que pasa → commit.

**Estado:** T01–T04 completados; T05–T09 en implementación activa.

**Objetivo:** G1–G7 de [GOALS](GOALS.md) con las decisiones D1–D4 de [AUTOPLAN-REVIEW](AUTOPLAN-REVIEW.md).
**Arquitectura:** monolito modular síncrono; core sin SDKs; SQLite (stdlib) detrás de puertos; runner de Telegram de un hilo.
**Términos:** [GLOSARIO](GLOSARIO.md). Rutas relativas a `src/incubia_orchestrator/` salvo `tests/`, `evals/` y `docs/`.
**Comando base:** `python -m pytest -q` (la red ya está bloqueada en `tests/conftest.py`). Cada tarea termina con la suite completa en verde y la CLI funcionando: `python -m incubia_orchestrator.interfaces.cli.main chat --fake`.

## Dependencias

```text
T01 → T02 → T03 → T04 ─┬→ T05 → T06 → T07 → T08 → T09 ═Gate A═ T10 → T11 ═Gate B═ T12 ═Gate C═
                        └→ (T05 y T06 requieren T03)
```

## H0

### T01 (E2-01) Contratos neutrales
- Crear `modules/conversation/domain/messages.py`: `InboundMessage(contract_version:int, channel:str, channel_account_ref:str, external_event_id:str, external_chat_ref:str, external_sender_ref:str, text:str, received_at:datetime)` y `ContextualizedResponse` (campos de BASE).
- Crear `modules/orchestration/domain/routing.py`: `RouteStatus(Enum)`, `RouteDecision` (invariante: `capability` presente si y solo si `RESOLVED`; `0 ≤ confidence ≤ 1`).
- Pruebas `tests/unit/test_e2_contracts.py`: round-trip JSON de cada tipo; `contract_version` desconocida → `UnsupportedContractVersion`; `RouteDecision(RESOLVED, None)` → `ValueError`; ningún módulo importa `telegram` ni `langgraph` (extender `tests/architecture`).
- Contratos de ADR-007 sin cambios: `tests/test_flow.py` debe seguir en verde sin editarlo.

### T02 (E2-02) Configuración versionada
- `config/e2/capabilities.yaml` (3 IDs de AGENTES), `config/e2/profiles/*.yaml`, `config/e2/bindings.example.yaml` (sin secretos) y `config/e2/budgets.yaml` (`cli`: 6/mes y 128 tokens; `eval-e2`: 150 llamadas, 400 tokens, `usd_cap: null`).
- Loader `bootstrap/config_e2.py` con validación estricta (añadir `PyYAML==6.0.3` como dependencia directa en `pyproject.toml`; hoy solo es transitiva): clave desconocida → error; `usd_cap: null` bloquea el modo `eval-e2`.
- Pruebas `tests/unit/test_config_e2.py`: perfil incompleto, versión duplicada, capability inexistente, `usd_cap` nulo con modo eval.
- Pendiente del responsable: fijar `usd_cap` antes de T12. Es el único valor que este plan no fija.

## H1

### T03 (E2-03) `SpecialtyProfile` y `AgentDescriptor`
- `modules/orchestration/domain/profile.py` y `descriptor.py` según GLOSARIO. `profiles_for(model)` queda como adaptador que lee la configuración (la CLI no cambia).
- Pruebas: los 3 perfiles cargan; el perfil no contiene `model`; añadir un `sales.advice@2` en un fixture no requiere editar `router.py` (lo verifica una prueba que hace grep del ID).

### T04 (E2-04) `ContextBuilder` y conversación canónica en memoria
- `modules/conversation/ports/repository.py` (`ConversationRepositoryPort`: `load(scope)`, `append_turn(scope, turn, expected_revision)`), adapter `adapters/persistence/memory.py`.
- `modules/orchestration/application/context_builder.py`: orden y presupuesto de AGENTES; el estimador `ceil(bytes/3)`; si lo obligatorio no cabe → `ContextOverflow`.
- Pruebas `tests/unit/test_context_builder.py`: 3 turnos; Ventas→Marketing→Ventas (canario `INSTR_VENTAS_XYZ` ausente en el contexto de Marketing); overflow; scope ajeno → vacío; `expected_revision` desfasada → `RevisionConflict`.

## H2

### T05 (E2-05) Routing
- `ports/decision_model.py`; `adapters/decision/fake.py` (tabla fija); `adapters/decision/openai_json.py` (reutiliza cliente y limitador de `openai_adapter.py`; JSON inválido o capability no elegible → AMBIGUOUS).
- `application/capability_resolver.py`: un comando explícito resuelve sin modelo; si no, llama al modelo.
- `evals/routing-v2.jsonl` (≥60 casos `val` + `dev`; esquema en GOALS) y script `evals/run_routing.py --adapter keywords|openai --split val` que imprime la matriz de confusión.
- Pruebas: con el fake, cada estado; con comando explícito, cero llamadas al modelo (contador del fake).

### T06 (E2-06) Discovery y Selection
- `ports/agent_discovery.py`, `adapters/registry/in_process.py`, `application/selection.py` (regla del GLOSARIO).
- Pruebas: descriptor deshabilitado excluido; scope ajeno excluido; dos versiones → elige la de mayor prioridad y, en empate, la regla estable; 0 candidatos → `UNSUPPORTED`.

### T07 (E2-07) Grafo delgado
- `nodes/select_specialty.py` deja de llamar al router: recibe la selección ya hecha en `StartExecutionRequest` mediante un campo nuevo versionado `selection` (opcional para la CLI vieja).
- Nuevo caso de uso `application/use_cases/handle_inbound.py`: resolve → discover → select → build context → `runtime.start`. `HandleMessage` queda como fachada CLI.
- Pruebas: PEP denegado en generación → `policy_denied` sin llamar al LLM; `tests/test_cli_offline.py` en verde sin cambios.

## H3

### T08 (E2-08) Contextualización y entrega neutral
- `modules/conversation/ports/response_context.py`, `ports/channel_delivery.py`; implementación in-process; dos adapters fake (`fake_a`, `fake_b`) en `tests/fakes/`.
- Pruebas: mismo outcome → misma `ContextualizedResponse` por ambos canales; canarios de instrucciones/policy ausentes del payload público.

### T09 (E2-09) SQLite, inbox/outbox y recuperación (Gate A)
- `adapters/persistence/sqlite/` con las tablas de BASE y las migraciones; dispatcher en `application/dispatch.py` con la tabla de errores de TELEGRAM.
- Pruebas `tests/integration/test_ledger.py` (archivo temporal y reapertura en un subproceso): mismo evento 2× → 1 ejecución y 1 turno; hash distinto → `IdempotencyConflict`; dos conexiones reservando el mismo evento → solo una gana; PROCESSING al reiniciar → NEEDS_INSPECTION; SENDING al reiniciar → UNKNOWN_EFFECT; FAILED transitorio respeta 3 intentos y el deadline.
- Gate A: anotar en VERIFICACION el commit, el comando y la salida.

## H4

### T10 (E2-10) Adapter Telegram y runner
- `modules/conversation/adapters/channels/telegram/{client.py,inbound.py,outbound.py}` con `httpx` (dependencia directa existente). `interfaces/cli/bot.py` expone `incubia-bot run|inspect|purge`.
- Token desde `TELEGRAM_BOT_TOKEN`; el logger redacta `bot<token>` en URLs.
- Pruebas con respuestas HTTP grabadas: mapping de update; no soportados → DISCARDED; offset solo tras el commit; 409 → salida con error; 429 → `next_attempt_at`; timeout → UNKNOWN_EFFECT; truncado a 4096 con Unicode (emoji).

### T11 (E2-11) Piloto Telegram + FakeLLM (Gate B)
- Ejecutar los pasos 2–4 y 6 de TELEGRAM § Prueba E2E; runbook `docs/roadmap/etapa-2/RUNBOOK.md` (arranque, parada, `inspect`, purga).

## H5

### T12 (E2-12) Evaluación real (Gate C)
- Requiere `usd_cap` registrado. `evals/run_routing.py --adapter openai --split val` y `evals/run_quality.py` (12 escenarios, rúbrica de GOALS, hoja de inspección manual en `evals/results/`).
- Informe de cierre según la plantilla de VERIFICACION.
