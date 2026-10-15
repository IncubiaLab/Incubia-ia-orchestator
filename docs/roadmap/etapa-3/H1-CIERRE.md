# Plan de cierre H1 — E3-1

Estado: expediente técnico listo para decisión. H1 permanece abierto sólo
hasta registrar la decisión formal E3-1 en `VERIFICACION.md`/Linear. La
preparación E3-H1-N y el slice de E3-03/04 fueron prerrequisitos, no equivalen
por sí solos al gate.

Estado de integración (2026-10-13): M1 está implementado localmente y la
campaña Neon `001`–`006` pasó 8/8. M2 quedó acreditado con restore de un scope
con una fila por tabla, import idempotente y RPO/RTO observado en
[e3-h1-m2-neon-2026-10-10.json](../../../evals/results/e3-h1-m2-neon-2026-10-10.json).
La campaña M3 integrada quedó `ready_for_gate`: offline 27/27, E3-D0-L
Compose passed y Neon 8/8. El artefacto no cierra el gate automáticamente;
falta registrar y revisar la decisión E3-1 en Linear.

## Resultado que debe acreditarse

E3-1 se cierra sólo cuando el ledger de Conversation conserva IDs, revisiones,
deduplicación y atomicidad en PostgreSQL/Neon; el rol runtime queda aislado
por RLS y sin DDL; los claims/fencing impiden commits obsoletos; y una
migración/restore sintética demuestra integridad, idempotencia, reconciliación,
RPO y RTO observados. No se aceptan filtros de aplicación como sustituto de
RLS ni credenciales en artefactos.

## Milestones

### M1 — Contrato compartido, ownership y fencing completo

**Alcance:** cerrar E3-03 y completar E3-04 sobre la rama `e3-h1-synthetic`.

**Implementación**

- Completar la matriz de contrato SQLite/PostgreSQL: reserve/replay,
  commit atómico, rollback, revisión obsoleta, recuperación y migraciones
  repetibles desde un esquema anterior.
- Integrar ownership persistente por cuenta Telegram y dispatcher con claims
  remotos; eliminar cualquier dependencia de locks sólo locales.
- Mantener `generation`, expiración basada en reloj de PostgreSQL y validación
  de claims de evento + conversación en el commit.
- Codificar la semántica de efectos inciertos: después de un envío remoto sin
  commit se registra `UNKNOWN_EFFECT`, y un outcome `SENT` no se reenvía.

**Evidencia de salida**

- Dos procesos que compiten por el mismo evento/conversación: un solo commit.
- Takeover después de expiración y rechazo de token obsoleto.
- Reinicio durante reserve, commit y envío: inbox/outbox/revisión recuperables.
- Reproducción de contrato en SQLite y Neon sin contaminación entre tenants ni
  conexiones reutilizadas.

**No cerrar M1 si:** falta el dispatcher persistente, se pierde la distinción
`UNKNOWN_EFFECT`/`SENT`, hay DDL con el rol runtime o una prueba depende de
consultas sin contexto scoped.

### M2 — Export/import, backup y restore medidos

**Alcance:** implementar E3-05 después de congelar el esquema y los contratos
de M1.

**Implementación**

- Crear export scoped con manifest de versión, deployment/tenant, conteos,
  hashes y rangos de revisión; excluir secretos y datos fuera del scope.
- Implementar import idempotente conservando IDs, claves de deduplicación,
  revisiones, inbox, outcomes y outbox.
- Rechazar hashes conflictivos y manifiestos incompletos sin dejar estado
  parcial; usar transacciones y una tabla/registro de importación auditable.
- Ejecutar backup y restore en una rama Neon aislada; reconciliar outbox y
  claims antes de devolver la rama a servicio.
- Medir RPO y RTO observados, incluyendo el punto de backup, el tiempo de
  recuperación y la validación posterior de readiness/ledger.

**Evidencia de salida**

- Segundo import del mismo manifest no duplica filas ni entregas lógicas.
- Manifest alterado o hash conflictivo falla de forma segura y reversible.
- Antes/después conserva IDs, revisiones, deduplicación e inbox/outbox.
- Restore validado en Neon con RPO/RTO, comandos, versiones y límites
  registrados.

**No cerrar M2 si:** el restore sólo se probó localmente, no existe evidencia
de Neon, hay pérdida de IDs/revisiones o la reconciliación puede reenviar una
entrega lógica.

### M3 — Campaña integrada y decisión E3-1

**Alcance:** ejecutar la campaña de cierre sobre datos sintéticos y formar el
expediente de gate.

**Implementación**

- Congelar commit, versiones de migraciones, configuración sanitizada y hash
  del dataset sintético.
- Ejecutar pruebas offline dirigidas, suite PostgreSQL y runner Neon opt-in
  con roles separados; repetir las pruebas sensibles a expiración en la misma
  rama temporal o en una rama sintética nueva si vence el TTL.
- Consolidar resultados de M1/M2 en `VERIFICACION.md`, `PROGRESS.md` y
  `RUNBOOK.md`: comandos reproducibles, n/denominadores, latencias, RPO/RTO,
  errores, límites y responsable.
- Revisar el checklist E3-1 y registrar en Linear la decisión de cierre,
  pendientes no bloqueantes y fecha de expiración de la evidencia.

**Criterio de cierre E3-1**

Todos los checks de persistencia, aislamiento, claims/fencing, migración y
restore pasan sin fallos críticos; el runtime no puede leer/escribir otro
tenant ni ejecutar DDL; no hay secretos en logs/artefactos; y el expediente
contiene evidencia Neon separada de cualquier evidencia Docker local.

**Expediente M3 vigente:**
[e3-1-campaign-2026-10-13-final.json](../../../evals/results/e3-1-campaign-2026-10-13-final.json).
Su `status` es `ready_for_gate` y `gate_closed` permanece `false` hasta la
decisión formal.

**Regla de bloqueo:** cualquier pérdida de datos, entrega duplicada, bypass de
RLS, commit con fencing vencido o RPO/RTO no medible detiene el cierre. Se abre
un ADR sólo si la resolución cambia el contrato, la topología o la autoridad
de escritura; los fallos de implementación se corrigen dentro de este plan.

## Roadmap de implementación

```text
M1. Contrato + ownership + fencing
  ├─ E3-03: equivalencia y recuperación
  └─ E3-04: dispatcher, UNKNOWN_EFFECT, SENT y claims
             │
             ▼
M2. Export/import + restore Neon
  ├─ manifest/hash/idempotencia/conflictos
  └─ backup, restore, reconciliación, RPO/RTO
             │
             ▼
M3. Campaña integrada E3-1
  ├─ offline + PostgreSQL + Neon sintético
  ├─ expediente sanitizado y reproducible
  └─ decisión de cierre registrada
```

La ejecución debe mantener una sola rama Neon sintética por campaña, no escribir
en `production`, y no avanzar a H2–H4 con la etiqueta E3-1 cerrada hasta que M3
esté firmado. El endpoint local D0 y pgvector no son dependencias de este plan.
