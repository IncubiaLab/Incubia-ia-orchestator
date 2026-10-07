# Runbook del piloto Telegram (Gate B)

Estado: listo para preflight; piloto real pendiente de token y dos bindings privados.

## Preparación

1. Usar un bot dedicado de prueba y dos participantes que aceptaron la ventana del piloto. Configurar `TELEGRAM_BOT_TOKEN` solo en el entorno del proceso.
2. Crear un archivo privado de bindings con el esquema de `config/e2/bindings.example.yaml`: exactamente dos filas, una cuenta de bot, chats privados, remitentes y tenants distintos. Mantenerlo fuera de Git.
3. Elegir una ruta local persistente para `--db`; comprobar permisos y respaldarla antes de la sesión. No ejecutar dos runners para la misma base.
4. Ejecutar `python -m incubia_orchestrator.interfaces.cli.bot inspect --db RUTA_DB` y resolver efectos inciertos antes de reanudar.

## Ejecución

`INCUBIA_ENV_FILE=.env python -m incubia_orchestrator.interfaces.cli.bot run --db RUTA_DB --bindings RUTA_PRIVADA`

El arranque hace `getMe` y comprueba que no exista webhook; si falla, se detiene. El proceso solo usa generación fake. Parar con Ctrl+C. No copiar URLs, token, IDs ni transcripciones a la evidencia.

## Evidencia de Gate B

Registrar fecha, commit, versión de bindings pseudonimizada, operador y ventana; tres turnos por participante, cambio Ventas/Marketing, aislamiento, rechazo de desconocidos, replay/reinicio desde fixture y estados de entrega. Los tests offline cubren 409, 429, timeout, duplicado y offset persistente. Registrar `UNKNOWN_EFFECT` como pendiente de inspección, sin reenvío automático.

Sin token o sin los dos bindings privados, Gate B permanece abierto.
