# Runbook — etapa 3

Estado: procedimiento objetivo, pendiente de ensayo. Ningún comando administrativo nuevo existe hasta la tarea que lo construye. La operación Telegram actual sigue [RUNBOOK E2](../etapa-2/RUNBOOK.md).

## E3-D0-L — baseline local Docker Compose

Este procedimiento acredita sólo el baseline local de instancia única. No es E3-0, no aprueba ADR-024, Kubernetes, réplicas, broker ni microservicios, y no sustituye la validación Neon/H1. Ejecutarlo exclusivamente con datos y scopes sintéticos. La publicación del servicio debe permanecer en `127.0.0.1`; el endpoint local sin autenticación está prohibido en staging y producción.

1. Preparar las variables locales de configuración y las dos credenciales de PostgreSQL (migrador y runtime) fuera del repositorio. No copiar secretos a la imagen, argumentos de build, logs ni evidencias.
   Copiar `deploy/e3-d0.env.example` a `deploy/e3-d0.env`, reemplazar valores URL-safe y usar siempre `docker compose --env-file deploy/e3-d0.env ...`; Compose no carga ese archivo anidado automáticamente.
2. Construir con `docker compose --env-file deploy/e3-d0.env build` y comprobar el usuario efectivo de `app`; debe ser no-root. Levantar `postgres`, esperar su healthcheck y ejecutar el servicio one-shot `migrate`; no iniciar `app` si ese paso falla.
3. Iniciar una sola instancia de `app`. Confirmar `GET /healthz` para proceso vivo y `GET /readyz` sólo después de configuración válida, schema aplicado y PostgreSQL accesible. Capturar los resultados sanitizados.
4. Enviar tres `POST /v1/executions` contra loopback con mensaje, `conversation_id` y la clave de idempotencia del transporte. No enviar `deployment_id`, `tenant_id` ni `actor_id`: el proceso toma ese scope sintético desde configuración. Comprobar un `execution_id` nuevo por request, el mismo `conversation_id`, ramas deterministas distintas y commit durable de inbox/turn/outcome/outbox/revisión.
5. Repetir exactamente un evento y comprobar una única incorporación lógica. Reiniciar sólo `app`, reenviar un nuevo turno de la conversación y comprobar que el historial/revisión persisten en PostgreSQL. Ensayar SIGTERM y revisar que el proceso queda recuperable al arrancar de nuevo.
6. Guardar build digest, configuración sanitizada, versiones de imagen/schema, comandos, IDs seudonimizados, logs sin secretos y resultado de la prueba de ausencia de red hacia LLM, Telegram, tools y Neon. No usar el resultado como evidencia de proveedores reales.

El script `scripts/e3/d0_smoke.sh` automatiza la evidencia L con un proyecto Compose temporal: build, preflight previo a migración, usuario no-root, health/readiness ante schema/DB ausente, cadena/replay/reinicio, recuperación de `PROCESSING`, SIGTERM, rechazo de identidad y logs. Requiere Docker Compose y `curl`; usa credenciales locales efímeras si no se exportan `D0_MIGRATOR_PASSWORD` y `D0_RUNTIME_PASSWORD`.

El hook que crea `d0_runtime` sólo se ejecuta al inicializar un volumen PostgreSQL vacío. Si se cambia una contraseña en `deploy/e3-d0.env`, no asumir que Compose rota el rol: rotarlo explícitamente con el rol migrador o recrear el volumen local sintético tras guardar o descartar su evidencia. Un volumen previo sin el rol hace fallar la migración de forma intencional; una contraseña runtime desactualizada mantiene `readyz` en error, sin iniciar tráfico.

El recorrido operativo es: `turno entrante → Contexto → eje de routing → capability/círculo → outcome → commit durable → siguiente turno`. El siguiente turno es otra solicitud HTTP: no se habilitan bucles internos ilimitados ni un contenedor por moneda, eje o círculo.

### E3-D0-R — posterior y separado

No ejecutar E3-D0-R antes de H1–H4, credenciales explícitamente autorizadas y presupuesto registrado. Reutiliza la imagen y el contrato HTTP de D0-L, sustituyendo adapters locales por Neon, pgvector, READ y LLM reales. Registrar auditoría, gasto y métricas en un artefacto separado. El resultado no cierra por sí solo G2–G9 ni E3-1…E3-5.

## Preparación

Operador registra entorno, deployment, tenant sintético, commit, versiones de schemas/adapters y responsable. Secretos: DATABASE_URL runtime y conexión migrador distintas; credenciales READ y embeddings/LLM por referencia. Verificar rol runtime limitado, TLS, región, límites de pool/cuota, retención y capacidad de restauración del plan Neon contratado. Config inválida o presupuesto real ausente bloquea arranque/red correspondiente.

Arranque: comprobar schema compatible, DB readiness y claims; reconciliar estados inciertos antes de polling/dispatch. Verificar binding y membresía; adquirir ownership exclusivo del bot. No lanzar segundo consumidor de Telegram ni webhook y polling a la vez.

## Migración SQLite → PostgreSQL

1. Gate A/B E2 acreditados y E3-1/2 sobre datos sintéticos; backup/restore ensayados. Designar una autoridad de escritura y una ventana de mantenimiento.
2. Detener consumo, pausar dispatcher y completar o clasificar operaciones en curso. Guardar offsets y manifest de IDs/revisiones/conteos. Mantener UNKNOWN_EFFECT en cuarentena.
3. Backup consistente SQLite y export scoped con hash; aplicar migraciones PostgreSQL con rol migrador. Importar idempotentemente y comparar claves, hashes, revisiones, inbox/outbox/offsets.
4. Verificar queries con rol runtime, tenants alternados y constraints. Reconciliar effects pendientes con historial remoto; ningún import dispara envíos.
5. Cambiar configuración a PostgreSQL, iniciar un consumidor y probar evento sintético nuevo/duplicado. Registrar decisión de autoridad, hora y checkpoint de corte.
6. Rollback solo si se detienen nuevas escrituras/entregas y se reconciliarán cambios posteriores al corte. Cambiar DATABASE_URL a un backup antiguo sin reconciliación puede duplicar efectos; mantener servicio pausado hasta resolver.

## Fallos y recuperación

| Evento | Acción |
| --- | --- |
| DB caída / pool saturado | Limitar admisión, dejar inbox/outbox durable, readiness false; no aceptar y confirmar eventos no persistidos. |
| PROCESSING tras caída | Inspección o reanudación conforme contrato validado; no repetir mutation por ausencia de outcome. |
| SENDING tras caída / respuesta remota perdida | UNKNOWN_EFFECT, detener retry de ese efecto, inspección auditada. |
| Claim vencido | Nuevo dueño solo con fencing; invalidar commits del anterior, sin presumir permiso de reenvío. |
| Credenciales/membresía revocadas | Bloquear siguiente acceso/entrega y purgar cache de permisos; revisar pendientes. |
| Índice incompleto | Mantener versión activa anterior; nueva versión no es consultable. |
| Fallo exportador de métricas | Buffer acotado/alerta; audit obligatorio en DB permanece autoridad. |

## Restore y retención

Restaurar en entorno aislado; medir punto restaurado y duración, validar esquema, conteos, claves y permisos. Poner entregas posteriores al punto de backup en cuarentena, reconciliar IDs/offsets/efectos y luego autorizar consumo. Registrar RPO/RTO observados. Una rama Neon por sí sola no demuestra restore ni backup independiente.

Retención E2 de 7 días payload / 30 tombstones es baseline sintético; E3-01 fija política por datos antes de clientes. Pending/UNKNOWN_EFFECT no se purgan sin resolución. Borrado abarca índices, cachés y backups según política; no prometer eliminación física instantánea. Export/restore nunca mezcla tenants por defecto.

## Release

Adjuntar VERIFICACION con G1–G9, gates, ADR aplicables, costos, incidentes y límites. Responsable registra GO de tráfico real y criterios de rollback. Arranque escalonado con alerta de duplicados, scope, errores y saturación; sin GO el estado permanece staging sintético. El Compose/E3-D0-L local no es un artefacto de release ni autorización para exponer su endpoint sin autenticación.
