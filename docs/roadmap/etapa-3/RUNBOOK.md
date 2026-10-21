# Runbook — etapa 3

Estado: E3-H1-N completó el preflight inicial; E3-03/04/05 tienen implementación local y pruebas dirigidas. ADR-ORCH-027 está Accepted. La campaña integrada del 2026-10-13 pasó offline (27/27), Compose local y Neon (8/8); H1 queda listo para decisión, con `gate_closed=false` hasta registrar E3-1. La operación Telegram actual sigue [RUNBOOK E2](../etapa-2/RUNBOOK.md).

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

La ejecución acreditada de M3 reutilizó la imagen ya construida para evitar una
segunda compilación: `E3_D0_PROJECT=incubia-e3-d0-final E3_D0_SKIP_BUILD=1
./scripts/e3/d0_smoke.sh`. Resultado: `E3-D0-L smoke passed` en 52.569 s.

El hook que crea `d0_runtime` sólo se ejecuta al inicializar un volumen PostgreSQL vacío. Si se cambia una contraseña en `deploy/e3-d0.env`, no asumir que Compose rota el rol: rotarlo explícitamente con el rol migrador o recrear el volumen local sintético tras guardar o descartar su evidencia. Un volumen previo sin el rol hace fallar la migración de forma intencional; una contraseña runtime desactualizada mantiene `readyz` en error, sin iniciar tráfico.

El recorrido operativo es: `turno entrante → Contexto → eje de routing → capability/círculo → outcome → commit durable → siguiente turno`. El siguiente turno es otra solicitud HTTP: no se habilitan bucles internos ilimitados ni un contenedor por moneda, eje o círculo.

### E3-D0-R — posterior y separado

No ejecutar E3-D0-R antes de H1–H4, credenciales explícitamente autorizadas y presupuesto registrado. Reutiliza la imagen y el contrato HTTP de D0-L, sustituyendo adapters locales por Neon, pgvector, READ y LLM reales. Registrar auditoría, gasto y métricas en un artefacto separado. El resultado no cierra por sí solo G2–G9 ni E3-1…E3-5.

### Probe local autenticado para integración real

`interfaces.http.e3_probe` es una entrada **separada** de D0, sólo para datos
sintéticos. Liga exclusivamente `127.0.0.1`/`::1`; exige Bearer token de al
menos 32 caracteres, opt-in `INCUBIA_E3_PROBE_REAL=1`, scope fijo de entorno,
DSN Knowledge runtime de Neon sintético (`sslmode=require`, rol no-owner), audit SQLite durable y presupuesto de embeddings con
límites positivos. `POST /v1/probe` acepta únicamente `query` y
`product_ref` numérico opcional. Con código de producto ejecuta Open Food Facts
v3 por Tool PEP; siempre consulta pgvector usando embeddings reales con cap
durable. El payload no puede elegir deployment, tenant ni actor. No genera LLM
ni escribe Knowledge/ledger; cada solicitud consume una reserva de embedding.

Copiar `deploy/e3-probe.env.example` a `deploy/e3-probe.env`, completar
credenciales y límites autorizados para esta campaña, y cargarlo en una shell
local protegida antes de ejecutar:

```bash
set -a
. deploy/e3-probe.env
set +a
python -m incubia_orchestrator.interfaces.http.e3_probe --host 127.0.0.1 --port 18081
```

En otra shell, enviar `Authorization: Bearer <token>` y JSON
`{"query":"consulta sintética","product_ref":"3017620422003"}` a
`http://127.0.0.1:18081/v1/probe`. `/readyz` exige token y comprueba el
schema Knowledge; `/healthz` sólo confirma proceso. No copiar token, DSN,
API key ni texto de respuesta a evidencia pública. Registrar IDs, audit,
presupuesto, latencias y errores de manera sanitizada. No exponer este probe
en staging/producción ni usarlo para declarar cerrado E3-5.

## Preparación

### E3-H1-N — preparación inicial de Neon

Esta preparación es infraestructura para E3-03/04/05, no evidencia de salida
E3-1. La rama `e3-h1-synthetic` deriva de `production`; la rama de trabajo
predeterminada no recibe escrituras de la campaña. El proyecto no cambia de
región ni plan. La expiración actual de la rama es de siete días y la ventana
PITR observada es de seis horas; el runbook de restore debe medir el alcance
real disponible, sin presentar esa ventana como backup independiente.

ADR-ORCH-027 ratifica provisioning SQL: los roles API iniciales con
`BYPASSRLS` fueron eliminados sin grants/uso y sustituidos por roles SQL con
`NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`. `incubia_runtime` tiene
`CONNECT` y `USAGE` pero no `CREATE` en `public`; `incubia_migrator` tiene
`CONNECT`, `USAGE` y `CREATE`. Ninguno es miembro de `neondb_owner`. El
preflight opt-in pasó runtime pooled TLS y migrador directo TLS. Los DSNs
están en `deploy/e3-neon.env` local, ignorado y modo `0600`; no copiarlos a
logs, capturas o chat. La medición TLS debe hacerse desde libpq cliente; la
vista `pg_stat_ssl` del backend a través del proxy no es equivalente.

Las migraciones `001_e3_d0_ledger.sql`, `002_e3_h1_rls.sql` y
`003_e3_h1_claims.sql` ya están aplicadas en la rama temporal. La campaña
final aplicó también `004_e3_h1_dispatcher_claims.sql` y
`005_e3_h1_backup.sql`; `002` protege
inbox, conversations, turns, outcomes y deliveries con RLS scoped por
deployment/tenant; el adapter fija ese scope sólo durante cada transacción.
`003` implementa leases y fencing iniciales para evento/conversación; todavía
no transfiere el ownership del consumidor Telegram ni modela dispatch remoto.

Desde la raíz del repo, operar con este procedimiento:

1. Instalar la dependencia de deployment del proyecto y preparar el entorno
   local con `uv run --isolated --extra deployment python scripts/e3/neon_h1.py prepare`.
   Este provisioning es de un solo uso y se niega a rotar roles/secretos si
   encuentra identidades existentes. El archivo resultante `deploy/e3-neon.env`
   debe permanecer ignorado por Git y en modo `0600`. No imprimir DSNs.
2. Copiar/usar `deploy/e3-neon.env.example` sólo como referencia. El archivo
   real lo genera el script después del preflight; no pegar secretos en chat,
   ADRs, logs, capturas ni argumentos.
3. Cargar el env local en la sesión del operador y habilitar únicamente la
   suite marcada Neon: `INCUBIA_E3_NEON_TESTS=1 INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic uv run --isolated --extra test --extra deployment python scripts/e3/run_neon_h1.py`.
   El runner rechaza cualquier host fuera de `*.neon.tech`, una rama distinta,
   roles inesperados, endpoint runtime no pooled o conexión migradora pooled.
   Las pruebas ordinarias siguen bloqueadas de red.
4. Antes de migrar, revisar que la rama no haya expirado y confirmar que sigue
   derivada del origen sintético. Si expiró, crear una nueva rama desde
   `production`, repetir la preparación y correr de nuevo la campaña; las
   migraciones se aplican por versión y los tests limpian sus filas sintéticas.
5. Aplicar migraciones sólo con `INCUBIA_MIGRATION_DATABASE_URL` directa y
   `incubia_migrator`; runtime usa `DATABASE_URL` pooled con TLS y no posee
   objetos ni `BYPASSRLS`. Contexto tenant/deployment debe configurarse dentro
   de cada transacción. Verificar que el mismo pooler soporte este patrón antes
   de habilitarlo para la aplicación.

La campaña posterior a M1 aplicó `004_e3_h1_dispatcher_claims.sql`,
`005_e3_h1_backup.sql` y la compatibilidad `006_e3_d0_runtime_claims.sql`, y
pasó 8/8 pruebas Neon. La prueba M2 exportó,
eliminó y restauró un scope sintético con una fila por tabla; el segundo import
del mismo manifest fue idempotente. RPO/RTO observados: 1.60/4.96 s y
9.94/4.32 s. El artefacto sanitizado está en
`evals/results/e3-h1-m2-neon-2026-10-10.json`.

No preparar pgvector ni una base Knowledge en H1; corresponde a H4/ADR-010.

Operador registra entorno, deployment, tenant sintético, commit, versiones de schemas/adapters y responsable. Secretos: `DATABASE_URL` runtime pooled y `INCUBIA_MIGRATION_DATABASE_URL` directa deben pertenecer a roles distintos; credenciales READ y embeddings/LLM por referencia. Verificar `rolsuper=false`, `rolbypassrls=false`, no ownership, TLS, región, límites de pool/cuota, retención y capacidad de restauración del plan Neon contratado. Config inválida o presupuesto real ausente bloquea arranque/red correspondiente.

Arranque: comprobar schema compatible, DB readiness y claims; reconciliar estados inciertos antes de polling/dispatch. Verificar binding y membresía; adquirir ownership exclusivo del bot. No lanzar segundo consumidor de Telegram ni webhook y polling a la vez.

## Migración SQLite → PostgreSQL

1. Gate A/B E2 acreditados y E3-1/2 sobre datos sintéticos; backup/restore ensayados. Designar una autoridad de escritura y una ventana de mantenimiento.
2. Detener consumo, pausar dispatcher y completar o clasificar operaciones en curso. Guardar offsets y manifest de IDs/revisiones/conteos. Mantener UNKNOWN_EFFECT en cuarentena.
3. Backup consistente SQLite y export scoped con hash; aplicar migraciones PostgreSQL con rol migrador. Importar idempotentemente y comparar claves, hashes, revisiones, inbox/outbox/offsets.
4. Verificar queries con rol runtime, tenants alternados y constraints. Reconciliar effects pendientes con historial remoto; ningún import dispara envíos.
5. Cambiar configuración a PostgreSQL, iniciar un consumidor y probar evento sintético nuevo/duplicado. Registrar decisión de autoridad, hora y checkpoint de corte.
6. Rollback solo si se detienen nuevas escrituras/entregas y se reconciliarán cambios posteriores al corte. Cambiar DATABASE_URL a un backup antiguo sin reconciliación puede duplicar efectos; mantener servicio pausado hasta resolver.

## Fallos y recuperación

### Campaña local E3-13

El runner `scripts/e3/load.py` acepta únicamente una URL HTTP loopback. Usa
mensajes sintéticos, un `conversation_id` por sesión y claves de idempotencia
únicas; guarda sólo IDs agregados, distribución de latencias, conteos HTTP y
snapshots de `/metrics`. Para comparar los dos perfiles de GOALS:

```bash
python scripts/e3/load.py --profile burst --sessions 80 --seed h5-burst-1 --output evals/results/e3-ops-burst.json
python scripts/e3/load.py --profile sessions --sessions 80 --duration 600 --interval 60 --seed h5-sessions-1 --output evals/results/e3-ops-sessions.json
```

Registrar también versión de imagen, CPU/memoria/pool, interrupción de DB,
restore y shutdown. El runner sólo mide el ingress D0 local con fakes; no
acredita comportamiento de proveedores, aislamiento Neon ni el gate E3-5.

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

### Rollback

Las migraciones (`migrations/postgres/001..007`, `migrations/knowledge/*`) son forward-only: no existen scripts *down*. El rollback se resuelve en dos capas independientes.

**Criterios para disparar.** Cualquiera durante el arranque escalonado o tras un release: duplicados de efecto o UNKNOWN_EFFECT por encima del baseline, violación de scope/RLS, readiness false sostenida, errores o saturación fuera de umbral, o falla de migración. Decide el responsable del GO y se registra en VERIFICACION con hora, versión de imagen y migración aplicada.

**1. Rollback de imagen (primera opción).** Detener admisión (readiness false), dejar inbox/outbox durable, desplegar la imagen N-1 por digest fijado (nunca `latest`) y reabrir admisión. No toca el esquema: es seguro porque el esquema N es compatible con la app N-1 por la regla siguiente. Pendientes en PROCESSING/SENDING se tratan como en "Fallos y recuperación"; no se reintenta un efecto por el cambio de versión.

**Regla expand/contract.** Toda migración es *expand* (tablas, columnas nullable o con default, índices, policies recreadas en el mismo archivo, `IF NOT EXISTS`). Un paso *contract* (DROP/RENAME de tabla o columna, cambio de tipo, `SET NOT NULL`, TRUNCATE/DELETE) solo se publica en un release posterior a que ninguna imagen desplegable lo necesite, con backfill previo y anotado aquí con la versión de app mínima. Baseline aceptado: los `SET NOT NULL` de scope en `002_e3_h1_rls.sql` y `006_e3_d0_runtime_claims.sql`, pre-release y precedidos de backfill. El check offline `tests/unit/test_e3_migration_rollback.py` falla ante cualquier paso no aditivo nuevo, policy eliminada sin recrear o DDL no idempotente.

**2. Rollback de esquema/datos (último recurso).** Solo si un contract o una corrupción impide operar a N-1. No se escribe SQL inverso a mano: se restaura.
1. Congelar escrituras (readiness false, workers detenidos) y exportar el estado actual por scope como evidencia: `scripts/e3/h1_backup.py export --deployment-id … --tenant-id … --output …`.
2. Crear DB/rama Neon aislada desde el punto previo al release (o vacía) y aplicar la cadena de migraciones hasta la versión que N-1 espera (las migraciones son idempotentes).
3. Restaurar el paquete del backup pre-release con `scripts/e3/h1_backup.py import --package … --database-url-env INCUBIA_MIGRATION_DATABASE_URL` (rol migrator); el restore valida manifest/hash, rechaza conflictos y deja auditoría en `restore_audit`.
4. Apuntar la imagen N-1 a la DB restaurada; las entregas posteriores al punto de backup quedan en cuarentena y se reconcilian (IDs/offsets/efectos) antes de autorizar consumo, como en "Restore y retención".

**Verificación post-rollback.** Readiness true con la imagen N-1; `schema_migrations` coincide con lo esperado; conteos y hashes por tabla del reporte de restore iguales al manifest; probe autenticado OK; RLS: consulta sin contexto de tenant devuelve cero filas; sin duplicados nuevos en deliveries; RPO/RTO observados registrados en VERIFICACION. Un rollback no ejecutado contra Neon real sigue siendo evidencia offline, no G de release.
