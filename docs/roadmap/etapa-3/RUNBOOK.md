# Runbook — etapa 3

Estado: procedimiento objetivo, pendiente de ensayo. Ningún comando administrativo nuevo existe hasta la tarea que lo construye. La operación Telegram actual sigue [RUNBOOK E2](../etapa-2/RUNBOOK.md).

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

Adjuntar VERIFICACION con G1–G9, gates, ADR aplicables, costos, incidentes y límites. Responsable registra GO de tráfico real y criterios de rollback. Arranque escalonado con alerta de duplicados, scope, errores y saturación; sin GO el estado permanece staging sintético.
