# Incubia Orchestrator — etapa 1

Chat local en terminal con LangGraph, tres perfiles (General, Ventas y Marketing) y un único modelo configurable. La ruta local `--fake` no usa red ni credenciales.

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

## Proveedor real

La API de OpenAI requiere `OPENAI_API_KEY` con facturación de API. La suscripción a ChatGPT/Codex no cubre esas llamadas. Ejemplo, tras configurar la variable de entorno en la sesión de shell:

```sh
.venv/bin/incubia chat --model gpt-4o-mini -m "hola"
```

`gpt-4o-mini` es el valor inicial; `INCUBIA_MODEL` o `--model` lo sustituyen para los tres perfiles. `--max-output-tokens` (512), `--timeout` (30 segundos por intento) y `--retries` (0) controlan el transporte. `--max-turns` (10 pares) y `--max-message-chars` (8000 caracteres por entrada) limitan la sesión. No hay deadline total del turno: con reintentos, la espera puede superar `--timeout`.

La respuesta va a stdout. stderr muestra `request_id`, estado, especialidad, latencia y tokens si el proveedor los informa. No se registran prompts, historial, respuestas ni claves. Para costo/latencia reales y estado de validación, véase [informe de etapa](docs/roadmap/etapa-1/VERIFICACION.md).

## Límites

Esta etapa no incluye API HTTP, base de datos, herramientas, RAG, autenticación ni persistencia. `resume` y aprobaciones están representados en contratos, pero no funcionan en este runtime local. La selección es una primera regla determinista evaluada con un conjunto pequeño de ejemplos, no una validación de calidad en producción.
