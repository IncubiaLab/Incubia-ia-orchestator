# Complemento al ROADMAP de la etapa 1 (resultado de /autoplan)

Fecha: 2026-10-01 · Rama: `dev/1-tier` · Estado: **pendiente de aprobación** (ver «Decisiones de gusto»).

Este documento no sustituye a [ROADMAP.md](ROADMAP.md). Lo complementa para que se cumpla [GOALS.md](GOALS.md). Restricción confirmada por el autor: **solo terminal, sin HTTP** en esta etapa.

Fases ejecutadas: CEO, Eng y DX, cada una con dos voces independientes (subagente Claude y Codex). Diseño omitido: no hay UI gráfica.

---

## 1. Resumen ejecutivo

El ROADMAP cubre bien la arquitectura (ADR-001/007) y el recorrido de construcción. Le faltan seis cosas que GOALS sí exige:

1. Un conjunto de evaluación etiquetado y versionado, con la métrica de routing (≥80 %).
2. Medición de latencia y costo por turno, con línea base.
3. Una taxonomía de fallos (configuración, proveedor, routing, entrada inválida) con política de timeout.
4. Logs con `request_id` y latencia, sin secretos ni contenido.
5. Una guía de arranque con variables de entorno y sesión de ejemplo.
6. Una forma de mostrar que no se usa la red en los tests.

Además hay **un hueco de contrato** que bloquea el hito 3: el ADR-ORCH-007 (aceptado) define una entrada de texto único y prohíbe `metadata: dict`, pero el chat necesita historial de turnos y devolver la especialidad elegida.

## 2. Revisión CEO

### Premisas

| # | Premisa | Estado |
| --- | --- | --- |
| P1 | Una CLI valida la orquestación antes que HTTP | **Confirmada por el autor** (solo terminal) |
| P2 | General / Arquitectura / Programación son una buena hipótesis | Aceptada como hipótesis; ver baseline (D-T1) |
| P3 | Routing por reglas deterministas basta al inicio | Aceptada; con eval versionado y partición de validación |
| P4 | Mantener LangGraph para un grafo corto | Aceptada (ADR-001 aceptado, no se reabre) |

### Consenso de las dos voces

```
CEO DUAL VOICES — CONSENSUS TABLE
  Dimensión                              Claude   Codex    Consenso
  1. ¿Premisas válidas?                  No       No       CONFIRMADO (sin probar)
  2. ¿Problema correcto?                 Dudoso   Dudoso   CONFIRMADO (falta tesis de usuario)
  3. ¿Alcance bien calibrado?            Sí*      Sí*      CONFIRMADO (*con huecos de GOALS)
  4. ¿Alternativas exploradas?           No       No       CONFIRMADO
  5. ¿Riesgos competitivos cubiertos?    No       No       CONFIRMADO (commodity)
  6. ¿Trayectoria a 6 meses sana?        Riesgo   Riesgo   CONFIRMADO
```

Hallazgos principales (ambas voces):

- **Lo que se valida es el router, no el valor de los especialistas.** Sin un brazo «solo General» no se sabe si tres perfiles mejoran algo. Corrección: añadir baseline (D-T1).
- **Medición circular.** Quien escribe las reglas escribe los ejemplos. Corrección: partición de validación escrita antes de afinar las reglas.
- **Alternativas no comparadas**: un único prompt sin grafo, clasificador LLM pequeño, máquina de estados simple. Se registran abajo; no se cambia la decisión.
- **Proposed ADR sin plazo.** 013, 017, 018, 019 y 020 guían el diseño sin fecha de ratificación. Corrección: ratificar o declarar excepción antes del hito 1.

### Alternativas consideradas (0C-bis)

| Opción | Esfuerzo | Riesgo | Veredicto |
| --- | --- | --- | --- |
| A. Grafo LangGraph + router por reglas (plan actual) | Medio | Router circular | **Elegida** (ADR-001) |
| B. Un único prompt sin grafo | Bajo | Contradice ADR-001 | Rechazada; se usa como **baseline de evaluación** |
| C. Clasificador LLM pequeño | Medio | Costo y latencia por turno, no determinista | Diferida; ADR de routing (ORCH-003) pendiente |
| D. Máquina de estados Python sin LangGraph | Bajo | Contradice ADR-001 | Rechazada |

### Fuera de alcance (reafirmado)

HTTP, UI, canales, RAG, tools, persistencia, multi-tenancy, autenticación, streaming, clasificador LLM, handoff, `resume()` funcional.

### Lo que ya existe

Solo documentación (ADR, specs, ROADMAP/GOALS/AGENTES). `src/` y `tests/` son esqueletos de carpetas vacías. No hay código que reutilizar.

### Delta del estado ideal

```
HOY: docs + carpetas vacías
  → ESTA ETAPA: CLI local, 3 perfiles, eval versionado, contratos propios probados
  → 12 MESES: HTTP/tenant/persistencia/RAG/handoff sobre los mismos contratos
```

## 3. Revisión de ingeniería

### Arquitectura propuesta

```
 interfaces/cli (argparse, REPL, stdout/stderr, exit codes)
        │ crea
        ▼
 application: ChatSession (historial acotado, en memoria)  ◄── dueño del historial
        │ SendTurn (use case): arma StartExecutionRequest
        ▼
 ports: WorkflowRuntimePort.start()      LLMPort.generate()
        ▲                                        ▲
        │ implementa                             │ implementa
 adapters/runtime/langgraph               adapters/llm/{openai,fake}
   START → select_specialty → generate_response → END
              │ llama a                      │ llama al puerto
              ▼                              ▼
   application: SpecialtyRouter           LLMPort
   (función pura, reglas + reason)

 bootstrap: único lugar que elige fake|openai, valida perfiles (1-3, General obligatorio, ≤3 modelos)
```

Decisiones de diseño (auto-decididas, ver auditoría):

- **El historial vive en Application** (`ChatSession`), no en LangGraph. El grafo no tiene estado entre turnos: sin checkpointer, sin reutilizar `thread_id`. Un turno fallido no se añade al historial.
- **La política de routing es una función pura en Application**, inyectada en el nodo `select_specialty`. El nodo solo la llama. Así el routing se prueba sin LangGraph. Un solo nodo `generate_response` parametrizado por perfil, no tres nodos.
- **Identidad en CLI**: `deployment_id="local"`, `tenant_id="local"`, `actor_id="cli-user"`; `conversation_id` por proceso; `execution_id` y `request_id` nuevos por turno. Generador de IDs inyectable para tests deterministas.
- **Puerto síncrono** en esta etapa (REPL con `input()`, `graph.invoke`, cliente OpenAI síncrono). Sin streaming; indicador «pensando…» en stderr.
- **`resume()`** devuelve `FailedExecution` con código «no soportado» y tiene su test de contrato. No `NotImplementedError`.

### Hueco de contrato (requiere decisión)

ADR-ORCH-007 está aceptado y no incluye historial ni especialidad. Propuesta de **adenda** (no cambia el espíritu del ADR; añade campos tipados):

- `StartExecutionRequest.input.history: tuple[ConversationTurn, ...]` con `role` y `text`.
- `CompletedExecution.output: AssistantMessage{text, specialty: SpecialtyId}`.
- `FailedExecution.specialty: SpecialtyId | None`, porque un fallo posterior al routing debe poder informarla.
- La razón/puntaje del routing se **registra en logs**, no viaja en el contrato.

### Consenso Eng

```
ENG DUAL VOICES — CONSENSUS TABLE
  Dimensión                       Claude   Codex    Consenso
  1. ¿Arquitectura sólida?        Con huecos  Con huecos  CONFIRMADO (historial/especialidad)
  2. ¿Cobertura de pruebas?       No       No       CONFIRMADO (red, historial, resume, arquitectura)
  3. ¿Riesgos de rendimiento?     Parcial  Parcial  CONFIRMADO (timeouts/reintentos)
  4. ¿Seguridad cubierta?         No       No       CONFIRMADO (logs, secretos)
  5. ¿Rutas de error manejadas?   No       No       CONFIRMADO (taxonomía)
  6. ¿Despliegue manejable?       Con huecos  Con huecos  CONFIRMADO (pinning/empaquetado)
```

### Taxonomía de errores y política de timeout

| Código | Origen | ¿Pasa por `start()`? | Mensaje CLI (problema · causa · acción) |
| --- | --- | --- | --- |
| `INPUT` | Vacío, demasiado largo, comando `/x` desconocido | No, se rechaza antes | `error[INPUT]: mensaje vacío. Escribe texto o /help.` |
| `CONFIG` | Falta clave, modelo no permitido, >3 perfiles o >3 modelos, falta General | No, falla al arrancar (exit 2) | `error[CONFIG]: falta OPENAI_API_KEY. Proveedor "openai". Exporta la variable o usa --fake.` |
| `PROVIDER` | Timeout, 429, 5xx, respuesta vacía, `finish_reason=length`, filtro de contenido | Sí, `FailedExecution` | `error[PROVIDER]: timeout tras 30s. Reintenta o sube INCUBIA_TIMEOUT_S. (request_id=…)` |
| `ROUTING` | Nunca llega al usuario: cae a General y lo indica como `general (fallback)` | n/a | Se registra el motivo |

Un error de autenticación del proveedor se clasifica como `CONFIG`, no `PROVIDER`.

Timeout: dos niveles. Por llamada al SDK (30 s por defecto) con **`max_retries=1` explícito** (el SDK de OpenAI reintenta dos veces por defecto y multiplica la latencia) y límite total por turno en el adapter. La sesión sigue usable tras un fallo.

### Historial

- Se acota por **número de turnos** (por defecto 10 pares), más un tope de caracteres por mensaje. Los tokens quedan diferidos porque exigen tokenizador por modelo. El roadmap decía «turnos o tokens»: se elige turnos.
- Se descarta siempre lo más antiguo y nunca se parte un par usuario/asistente.
- Todos los perfiles reciben la misma ventana. Se elimina la promesa de «contexto relevante» de AGENTES.md porque no tiene definición verificable.

### Casos límite

| Caso | Comportamiento esperado |
| --- | --- |
| Línea vacía o solo espacios | `INPUT`, sin llamar al LLM ni tocar historial |
| Entrada muy larga | `INPUT` con el tope |
| `/algo` desconocido | Ayuda; nunca llega al LLM |
| Ctrl-D (EOF) | Salida limpia, exit 0 |
| Ctrl-C en el prompt | Línea nueva, exit 130, sin traceback |
| Ctrl-C durante una llamada | Cancela el turno, la sesión sigue, no se añade medio turno |
| stdin no interactivo | Sin banner ni prompt; lee hasta EOF |
| >3 perfiles, 0 perfiles, ids duplicados, sin General | Fallo de arranque `CONFIG`, exit 2 |
| Salida truncada (`finish_reason=length`) | `PROVIDER` con mensaje específico |

### Seguridad

- El router es determinista y no usa LLM: el usuario no puede inducirlo a acciones. El riesgo es solo errar de perfil, de bajo impacto porque los perfiles no tienen tools. Normalización NFKC y comparación sin distinguir mayúsculas.
- El texto del usuario va solo en rol `user`, nunca interpolado en el prompt de sistema.
- Secretos solo desde entorno; envoltorio con `repr` enmascarado; no se registran excepciones completas, solo clase y código mapeado. Loggers `httpx` y `openai` en WARNING.
- `.env` en `.gitignore`; `.env.example` solo con marcadores.

### Registro de modos de fallo

| Fallo | ¿Probado? | ¿Manejado? | ¿Visible al usuario? | Brecha |
| --- | --- | --- | --- | --- |
| Timeout del proveedor | Pendiente | Plan | Sí | Falta test con fake bloqueante |
| Clave ausente | Pendiente | Plan | Sí | Falla al arrancar, no en el primer turno |
| Fuga de secreto en logs | Pendiente | Plan | No | **Crítica**: test con secreto canario |
| Fuga de contenido en logs | Pendiente | Plan | No | **Crítica**: GOALS lo exige |
| Red usada por error en tests | Pendiente | Plan | No | **Crítica**: guardia de sockets |
| Historial desbordado | Pendiente | Plan | No | Test de límites N, N+1, 0 |
| Import de LangGraph desde Application | Pendiente | Plan | No | Test de arquitectura |

### Diagrama de cobertura de pruebas

```
CLI (main con streams inyectados)
 ├─ /help, /exit, EOF, línea vacía, /desconocido ........ unit
 ├─ conversación de 3 turnos ............................ e2e fake  (GOALS 1)
 ├─ salida: respuesta en stdout, pie en stderr ......... subprocess (smoke del entrypoint)
 └─ códigos de salida 0 / 2 / 130 ....................... unit
SendTurn / ChatSession
 ├─ ventana de historial (0, N, N+1, mensaje enorme) .... unit
 ├─ turno fallido no entra al historial ................. unit
 └─ IDs: request_id y execution_id por turno, conversation_id estable ... unit
SpecialtyRouter
 ├─ ejemplos por especialidad + ambiguo → General ....... unit  (GOALS 2)
 └─ eval versionado ≥80 % (validación aparte) ........... eval  (GOALS medición)
WorkflowRuntimePort (contrato)
 ├─ completed / failed / suspended ...................... contract (fake runtime + LangGraph)
 ├─ resume() → Failed(no soportado) ..................... contract
 └─ serialización JSON de los contratos ................. contract
LLMPort (contrato)
 ├─ FakeLLM y adapter OpenAI con transporte simulado .... contract (timeout, 429, 500, vacío)
 └─ usage de tokens presente ............................ contract
Arquitectura
 ├─ domain/application sin langgraph, langchain, openai, fastapi, qdrant, redis ... architecture (GOALS 4)
 └─ interfaces/cli tampoco importa openai ni langgraph ... architecture
Red y secretos
 ├─ guardia autouse que rompe socket.connect y getaddrinfo ... GOALS 6
 ├─ test que prueba que la guardia funciona ...................
 └─ canario de secreto y de contenido ausente en logs/stdout/stderr ... GOALS 5
```

Test plan en disco: `~/.gstack/projects/hhce2303-Incubia-ia-orchestator/dev-1-tier-test-plan-20261001.md`.

### Empaquetado y versiones

- `pyproject.toml` con `requires-python = ">=3.12,<3.13"` y `[project.scripts] incubia = "incubia_orchestrator.interfaces.cli.main:main"`.
- Fichero de bloqueo (`uv.lock` recomendado) con versión exacta de `langgraph` y `openai`. Usar el SDK `openai` sin `langchain-openai`.
- `__init__.py` en todos los niveles bajo `src/` (setuptools los omite en silencio si faltan).
- Hito 1 incluye una **prueba de compatibilidad concreta**: compilar e invocar el grafo mínimo con FakeLLM.
- `__main__.py` para `python -m incubia_orchestrator`.
- Prueba del entrypoint instalado en un venv limpio.

## 4. Revisión DX

```
DX DUAL VOICES — CONSENSUS TABLE
  Dimensión                       Claude   Codex    Consenso
  1. ¿Primer turno < 5 min?       No       No       CONFIRMADO
  2. ¿Nombres de CLI adivinables? Sí       Sí       CONFIRMADO (distinguir --help de /help)
  3. ¿Errores accionables?        No       No       CONFIRMADO
  4. ¿Docs encontrables?          No       No       CONFIRMADO
  5. ¿Ruta de actualización?      N/A      Parcial  N/A en etapa local
  6. ¿Entorno sin fricción?       No       No       CONFIRMADO (sin clave no hay demo)
```

Puntuación DX: **5/10 en el plan actual → 8/10 con los cambios**. TTHW objetivo: **menos de 3 min y 4 comandos en modo demo; menos de 5 min con OpenAI.**

### Interfaz de línea de comandos

| Elemento | Propuesta |
| --- | --- |
| Comando | `incubia chat`, también `python -m incubia_orchestrator` |
| Opciones | `--fake`, `--no-meta`, `--profile`, `--debug`, `--version`, `-m "texto"` (un solo turno) |
| Comandos dentro del chat | `/help`, `/exit` (alias `/quit`), `/reset` |
| stdout | Solo la respuesta del asistente |
| stderr | Pie `[especialidad · request_id · latencia]`, banner, errores |
| Códigos de salida | 0 correcto · 2 uso o configuración · 3 fallo de proveedor en modo un-turno · 130 SIGINT |
| Modo demo | `--fake` o `INCUBIA_LLM_PROVIDER=fake`; el fake responde con el nombre del perfil para que el routing sea visible sin clave |

### Variables de entorno

| Variable | Por defecto | Uso |
| --- | --- | --- |
| `INCUBIA_LLM_PROVIDER` | `openai` | `openai` o `fake` |
| `OPENAI_API_KEY` | (ninguno) | Obligatoria con `openai` |
| `INCUBIA_MODEL_GENERAL`, `_ARQUITECTURA`, `_PROGRAMACION` | un modelo compartido, fijado al implementar | Máx. 3 valores distintos |
| `INCUBIA_MAX_OUTPUT_TOKENS` | 1024 | Tope de salida |
| `INCUBIA_TIMEOUT_S` | 30 | Timeout por llamada |
| `INCUBIA_HISTORY_TURNS` | 10 | Ventana de historial |
| `INCUBIA_TEMPERATURE` | 0.2 | |
| `INCUBIA_LOG_LEVEL` | `WARNING` | |
| `INCUBIA_DEBUG` | 0 | Muestra regla y puntuación de routing, sin contenido |

Se respeta `NO_COLOR`. `.env.example` solo con marcadores.

### Sesión de ejemplo (la guía de arranque la reproduce con salida real)

```
$ incubia chat --fake
incubia 0.1 [demo: LLM falso] — /help para ayuda, /exit para salir
> ¿Cómo diseño el contrato entre application y el runtime?
(respuesta)
[arquitectura · req_8f3a21 · 0.4s]
> ¿por qué me falla este KeyError en mi dict?
(respuesta)
[programacion · req_9b02c7 · 0.3s]
> hola
(respuesta)
[general (fallback) · req_1c44de · 0.2s]
> /exit
```

### Documentación a entregar

- `docs/QUICKSTART.md`: requisitos, instalación, demo, tabla de variables, sesión de ejemplo, tabla de errores con su solución, cómo ejecutar tests sin red.
- `CONTRIBUTING.md` breve: estructura y regla de aislamiento de LangGraph, cómo añadir una especialidad, cómo correr el eval.
- Tabla de estado de ADR (aceptado / propuesto) en el README.

## 5. Trazabilidad GOALS → ROADMAP complementado

| Objetivo de GOALS | Estado en ROADMAP original | Cambio propuesto | Hito |
| --- | --- | --- | --- |
| 1. Experiencia: ≥3 turnos, ayuda y salida | Parcial («varios turnos») | Test e2e de 3 turnos con FakeLLM; ventana verificada en el tercer turno | 2 y 4 |
| 2. Orquestación: especialidad por turno, ejemplos y ambiguo | Parcial | Fixtures por especialidad y ambiguo; especialidad tipada en el outcome | 3 |
| 3. Alcance: 1-3 perfiles, cero tools/BD/canales | Texto sin verificación | Validador de arranque y test que rechaza >3 perfiles o >3 modelos | 1 |
| 4. Arquitectura: ADR-001/007, contratos propios | Texto sin verificación | Test de arquitectura y de serialización; adenda a ADR-007 | 1 |
| 5. Confiabilidad: error seguro, `request_id`, latencia | Sin plan de logs ni timeouts | Taxonomía, política de timeout, logging estructurado, tests de canario | 1-4 |
| 6. Reproducibilidad: tests sin red ni credenciales | Declarado sin prueba | Guardia de sockets y test de la guardia | 4 |
| Medición: conjunto etiquetado ≥80 % | **Ausente** | `evals/routing_v1.jsonl` versionado, script de precisión, partición de validación | 3-4 |
| Medición: latencia y costo por turno | **Ausente** | `usage` y `latency_ms` en el puerto; informe de línea base manual | 4 |
| Medición: fallos por tipo | **Ausente** | Códigos `CONFIG`, `PROVIDER`, `ROUTING`, `INPUT` y conteo en el log | 2 |
| Definición de terminado: guía de arranque | **Ausente** | `docs/QUICKSTART.md` | 4 |
| Definición de terminado: ningún ADR propuesto como aceptado | Solo texto | Tabla de estado y ratificar-o-excepción antes del hito 1 | 0 |

### Hitos actualizados (delta sobre el ROADMAP)

- **Hito 0**: ratificar o declarar excepción para ADR 013/017/018/019/020; redactar adenda a ADR-007; fijar el perfil de identidad local.
- **Hito 1**: contratos con historial y especialidad tipados; `LLMPort` con `usage`, errores cerrados y timeout; validador de perfiles; bloqueo de versiones; prueba de compatibilidad de LangGraph; test de arquitectura; guardia de sockets.
- **Hito 2**: `incubia chat --fake` funciona sin variables de entorno; formato stdout/stderr; códigos de salida; logging estructurado sin contenido ni secretos.
- **Hito 3**: `SpecialtyRouter` puro; grafo con `select_specialty` y `generate_response`; eval versionado con partición de validación y brazo baseline.
- **Hito 4**: suite completa, informe de línea base de latencia y costo, `QUICKSTART.md`, `CONTRIBUTING.md`.

## 6. Decisiones de gusto (a revisar en la puerta final)

| ID | Decisión | Recomendada | Alternativa |
| --- | --- | --- | --- |
| T1 | Brazo baseline «solo General» en el eval | Sí | Medir solo precisión de routing (cumple el texto de GOALS, no prueba valor) |
| T2 | Puerto síncrono ahora | Síncrono | `async def start` desde el inicio; evita migrar después, pero complica REPL y Ctrl-C |
| T3 | Forma de la adenda a ADR-007 | Campos tipados `history` y `specialty` | Pasar `ConversationContext` como campo propio de `StartExecutionRequest` |
| T4 | Sin clave: modo demo automático o error | Error `CONFIG` claro sugiriendo `--fake` | Caer a fake con banner; más cómodo pero puede ocultar una mala configuración |
| T5 | Partición de validación del eval | Sí, escrita antes de afinar reglas | Un solo conjunto |

## 7. Registro de decisiones

| # | Fase | Decisión | Clase | Principio | Motivo | Rechazado |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | CEO | Aceptar P1-P4 | Mecánica | P6 | El autor confirmó solo terminal; ADR-001 aceptado | Reabrir ADR |
| 2 | CEO | Eval versionado con partición | Mecánica | P1 | GOALS lo exige; ambas voces coinciden | Solo casos ad hoc |
| 3 | CEO | Ratificar o excepción de ADR propuestos en hito 0 | Mecánica | P1 | Evita arrastrar decisiones sin dueño | Dejar abierto |
| 4 | Eng | Historial en Application, grafo sin estado | Mecánica | P5 | Alineado con ADR-001 e ADR-019 | Checkpointer de LangGraph |
| 5 | Eng | Routing como función pura inyectada | Mecánica | P5 | Testeable sin LangGraph | Reglas dentro del nodo |
| 6 | Eng | Adenda tipada a ADR-007 | Gusto (T3) | P5 | Sin ella no hay historial ni especialidad | Diccionario de metadatos |
| 7 | Eng | Identidad local por constantes | Mecánica | P3 | No bifurcar un contrato aceptado | Eliminar campos de scope |
| 8 | Eng | Puerto síncrono | Gusto (T2) | P3 | REPL simple | Async desde el inicio |
| 9 | Eng | Historial por turnos | Mecánica | P3 | Tokens requieren tokenizador por modelo | Límite por tokens |
| 10 | Eng | `max_retries=1` explícito | Mecánica | P1 | El SDK reintenta 2 veces por defecto | Valor por defecto |
| 11 | Eng | Taxonomía `INPUT/CONFIG/PROVIDER/ROUTING` | Mecánica | P1 | GOALS la nombra | Error genérico |
| 12 | Eng | Guardia de sockets y canarios | Mecánica | P1 | GOALS 5 y 6 | Confiar en no tener clave |
| 13 | Eng | `uv.lock` y rango de Python | Mecánica | P5 | Reproducibilidad | Versiones sueltas |
| 14 | Eng | `resume()` → Failed no soportado | Mecánica | P5 | Contrato completo sin falsa capacidad | `NotImplementedError` |
| 15 | DX | Respuesta en stdout, pie en stderr | Mecánica | P5 | Se puede canalizar | Todo en stdout |
| 16 | DX | Modo `--fake` explícito | Mecánica | P1 | Demo sin clave | Solo tests |
| 17 | DX | Sin clave: error `CONFIG` | Gusto (T4) | P5 | No ocultar mala configuración | Caer a fake |
| 18 | DX | Quickstart y CONTRIBUTING | Mecánica | P1 | Definición de terminado | Solo README |
| 19 | CEO | Baseline «solo General» | Gusto (T1) | P1 | Hace falsable el objetivo | No comparar |

## 8. Tareas de implementación (por prioridad)

- [ ] **P1** Adenda a ADR-007 e implementación de contratos con historial y especialidad (hito 0-1)
- [ ] **P1** `ChatSession` y `SendTurn` en Application; grafo sin estado (hito 1-2)
- [ ] **P1** `LLMPort` con `usage`, errores cerrados y timeout; FakeLLM y adapter OpenAI (hito 1)
- [ ] **P1** Guardia de sockets y test de arquitectura (hito 1)
- [ ] **P1** `evals/routing_v1.jsonl` con partición de validación y script de precisión (hito 3-4)
- [ ] **P1** Logging estructurado sin contenido ni secretos, con test de canario (hito 2)
- [ ] **P2** CLI: formato, códigos de salida, `--fake`, `-m`, `/reset` (hito 2)
- [ ] **P2** Validador de perfiles y modelos en bootstrap (hito 1)
- [ ] **P2** Empaquetado, `uv.lock`, prueba del entrypoint instalado (hito 1)
- [ ] **P2** Informe de línea base de latencia y costo (hito 4)
- [ ] **P3** `QUICKSTART.md`, `CONTRIBUTING.md`, tabla de estado de ADR (hito 4)

## 9. Temas transversales

- **Contrato vs. CLI** (CEO y Eng): el contrato aceptado no describe lo que el chat necesita. Señal alta.
- **Medición no probada** (CEO, Eng y DX): el eval, la red y los logs se declaran en GOALS pero nada los comprueba. Señal alta.
