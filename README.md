# Incubia Orchestrator — etapa 1

La [guía del código](docs/codigo/README.md) recorre los módulos, el flujo del chatbot y las decisiones que explican su implementación.

Chat local en terminal con LangGraph, tres perfiles (General, Ventas y Marketing) y un único modelo configurable. La ruta local `--fake` no usa red ni credenciales.

La [planificación de etapa 2](docs/roadmap/etapa-2/ROADMAP.md) desarrolla especialistas con contexto propio, routing por capacidades y el primer adaptador Telegram E2E sobre contratos multicanal. Es un roadmap propuesto; las instrucciones de ejecución siguientes corresponden a etapa 1.

## Preparación

Requiere Python 3.12. Desde la raíz del repositorio:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/incubia chat --fake -m "quiero vender"
```

`requirements.lock` fija las dependencias de ejecución y de pruebas; `requirements.txt` lo referencia. El paquete se instala con `--no-deps` para respetar ese bloqueo. Para comprobar la instalación:

```sh
.venv/bin/python -m pytest -q
.venv/bin/incubia chat --fake
```

El REPL acepta `/help`, `/exit` y EOF. Un proceso nuevo inicia una conversación vacía. El fake responde indicando el perfil elegido. Las solicitudes con señales de ventas y marketing, o sin señales, van a General.

Para depuración en la terminal, toda respuesta con especialidad seleccionada se identifica con `[General.specialist]`, `[Sales.specialist]` o `[Marketing.specialist]` antes del texto generado.

## Telegram

El runner `incubia-bot` usa long polling, el runtime de routing/policy/LangGraph y OpenAI por defecto. La entrada queda protegida por una allowlist de chats privados: copia `config/e2/bindings.example.yaml` a `config/e2/bindings.yaml` y reemplaza `external_chat_ref` y `external_sender_ref` por los ids autorizados.

Para obtener esos ids sin consumir el update ni responderlo, envía `/start` al bot y ejecuta:

```sh
uv run --project . --extra test incubia-bot discover
```

Con `TELEGRAM_BOT_TOKEN` y `OPENAI_API_KEY` en `.env`, inicia el bot así:

```sh
uv run --project . --extra test incubia-bot run --bindings config/e2/bindings.yaml
```

Para aceptar varios chats privados con una sesión aislada por chat, usa el modo explícito `--multi-session` (puedes omitir `--bindings`):

```sh
uv run --project . --extra test incubia-bot run --multi-session
```

Cada chat obtiene su propio `conversation_id`, `actor_id`, historial y scope. Si necesitas una allowlist cerrada, conserva `--bindings` y añade una fila por sesión.

Para comprobar Telegram sin consumir API de OpenAI:

```sh
uv run --project . --extra test incubia-bot run --fake --once --bindings config/e2/bindings.yaml
```

El ledger SQLite conserva inbox/outbox, deduplicación y el historial por conversación en `~/.local/state/incubia/telegram.sqlite3`. `--once` procesa los updates pendientes y termina; sin esa opción el proceso continúa haciendo polling. No habilites un webhook ni ejecutes dos runners para el mismo bot.

## Orbit sobre el runtime compartido

Orbit puede usar el mismo runtime de generación sin entregar la conversación por Telegram. El adaptador HTTP autenticado recibe del BFF la identidad y la evidencia que Orbit ya autorizó, ejecuta `compose_scoped` y devuelve `text/event-stream` para que las respuestas aparezcan en el chat de Orbit. Este endpoint no consulta la base de Orbit, no acepta credenciales del usuario final y no envía mensajes a Telegram.

Configura `INCUBIA_ORBIT_GATEWAY_TOKEN` con un secreto aleatorio de al menos 32 caracteres y ejecuta `uv run incubia-orbit-gateway --host 0.0.0.0 --port 8081` dentro de una red privada entre Fly y el BFF. Mantén el secreto solo en ambos runtimes; el frontend nunca lo recibe. `INCUBIA_ORBIT_GATEWAY_DEPLOYMENT_ID` es opcional (por defecto `incubia-orbit`). `INCUBIA_ORBIT_GATEWAY_FAKE=1` sirve únicamente para desarrollo y devuelve respuestas fijas sin ejecutar ni repetir el prompt interno. El endpoint `POST /v1/turns` emite eventos `delta`, `citation` (solo IDs presentes en la evidencia recibida) y `done`; `/healthz` y `/readyz` sirven para probes.

El endpoint valida un máximo de 20 elementos y 60 000 caracteres de evidencia, limita a 8 generaciones simultáneas y exige Bearer auth. El BFF debe construir el body desde su propia identidad y autorización, nunca reenviar permisos escogidos por el navegador. El modo SSE actual entrega los eventos después de completar la generación; la cancelación durante una inferencia y el streaming incremental del proveedor quedan pendientes.

### Knowledge Base de Orbit

La decisión de almacenamiento para Orbit está registrada en [ADR-KB-NEON-OBJECT-STORAGE](../Incubia%20Orbit/ADR-KB-NEON-OBJECT-STORAGE.md): los originales vivirán en el bucket privado `incubia-knowledge` de Neon Object Storage y el índice semántico continuará en Neon Postgres/pgvector. `neon.ts` declara el bucket para las ramas de este proyecto. La carga, lectura S3, extracción de texto e indexación desde el gateway aún requieren implementación; el gateway actual solo consume la evidencia ya autorizada que Orbit adjunta a cada turno.

## Proveedor real

La API de OpenAI requiere `OPENAI_API_KEY` y saldo de API. La aplicación lee `OPENAI_API_KEY` e `INCUBIA_MODEL` desde `.env` en el directorio actual si no están definidos en la shell. La suscripción a ChatGPT/Codex no cubre esas llamadas. Ejemplo:

```sh
.venv/bin/incubia chat --model gpt-4o-mini -m "hola"
```

`gpt-4o-mini` es el valor inicial; `INCUBIA_MODEL` o `--model` lo sustituyen para los tres perfiles. En modo real se aplican límites que la CLI no permite ampliar: **20 intentos de API por mes UTC**, **10 segundos entre intentos**, **128 tokens de salida**, **500 caracteres por mensaje**, **2 pares de historial** y **cero reintentos**. Los intentos fallidos también consumen el cupo local. El contador persiste en `~/.local/state/incubia/api-budget.json` y solo protege las llamadas hechas por esta aplicación; no representa el saldo ni el gasto de toda la cuenta. `--timeout` limita cada intento a 30 segundos por defecto. En `--fake` siguen disponibles los límites amplios de la demo.

Un `PROVIDER_QUOTA` indica saldo de API agotado; se distingue de `PROVIDER_RATE_LIMIT`. La terminal muestra sólo las respuestas del chat. Las métricas operativas (`request_id`, estado, especialidad, latencia y tokens) se guardan como JSON Lines en `logs/incubia-cli.log`, un directorio ignorado por Git; se puede cambiar la ubicación con `INCUBIA_LOG_FILE`. No se registran prompts, historial, respuestas ni claves. Para costo/latencia reales y estado de validación, véase [informe de etapa](docs/roadmap/etapa-1/VERIFICACION.md).

## Límites

El gateway Orbit es una interfaz de servicio acotada, no una API general del Orchestrator. No incluye base de datos propia ni sustituye la autenticación/autorización del BFF. `resume` y aprobaciones están representados en contratos, pero no funcionan en este runtime local. La selección es una primera regla determinista evaluada con un conjunto pequeño de ejemplos, no una validación de calidad en producción.

Si la API devuelve `PROVIDER_QUOTA`, revisar el saldo de la **organización/proyecto de API**, no la fecha de creación ni el gasto mostrado en la lista de claves. Una clave activa con gasto $0.00 puede pertenecer a una organización sin crédito prepago. El [informe](docs/roadmap/etapa-1/VERIFICACION.md) registra el fallo inicial por cuota y las pruebas reales posteriores con saldo.
