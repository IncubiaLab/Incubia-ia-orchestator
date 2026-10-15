# E3-H1-N — preflight de Neon

**Fecha de inspección:** 2026-10-09/10 UTC  
**Estado:** preparación inicial documentada; la campaña integrada posterior
acreditó el slice completo en la rama sintética. Este preflight no es por sí
solo evidencia de cierre de E3-1.

## Proyecto y rama

| Campo | Valor observado |
| --- | --- |
| Proyecto | Incubia Lab (`dawn-thunder-41457275`) |
| Rama predeterminada/origen | `production` — confirmada por el operador como sintética |
| Rama de campaña | `e3-h1-synthetic`, derivada de `production`, estado `ready` |
| Región | `aws-us-east-2` |
| PostgreSQL | 18 |
| Plan | Free (`free_v3`) |
| Compute | Autoscaling: 0.25–2 CU; suspensión automática desactivada |
| PITR/historial | 21 600 s (6 h) |
| TTL de rama | 604 799 s (7 días menos 1 s) |
| Expiración observada | `2026-10-16T04:19:47Z` |
| Base existente | `neondb`; se reservará para Control Plane |
| Escrituras en `production` | Ninguna atribuible a esta campaña; rama de trabajo aislada |

No se alteraron región, plan, compute ni retención. El historial de seis horas
limita el ensayo de PITR y no equivale a backup independiente. No se creó una
base de Knowledge ni se habilitó pgvector.

## Roles, grants y conexiones

Neon CLI 8.3.3 creó inicialmente `incubia_runtime` e `incubia_migrator`, pero
ambos mostraron `CREATEDB`, `CREATEROLE` y `BYPASSRLS`. `neondb_owner` no pudo
reducir los privilegios (`InsufficientPrivilege`); los dos roles API se
eliminaron antes de grants o uso. Tras ratificar ADR-ORCH-027, se crearon por
SQL con `LOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`.

Se concedió `CONNECT` a ambos roles; `CREATE` sobre schema `public` sólo al
migrador, y al runtime únicamente `USAGE`. También se revocó el `CREATE` de
`PUBLIC` en `public` en esta rama sintética dedicada. Se verificó ausencia de
membresía `neondb_owner`, y que runtime no puede crear objetos mientras el
migrador sí puede ejecutar DDL en el schema.

Los DSNs separados están en `deploy/e3-neon.env`, ignorado por Git y modo
`0600`; nunca se imprimieron en salida ni evidencia. El preflight opt-in
`scripts/e3/run_neon_h1.py` confirmó runtime pooled y migrador por endpoint
directo, ambos contra `neondb`, con TLS observado desde libpq en el tramo
cliente→Neon. La consulta previa a
`pg_stat_ssl` devolvió `false`; ese valor observa el backend detrás del proxy,
así que el test se corrigió para consultar el estado TLS del cliente.

Se aplicaron `001_e3_d0_ledger.sql`, `002_e3_h1_rls.sql` y
`003_e3_h1_claims.sql` mediante el rol migrador; `PostgresLedger.migrate` omite
versiones ya registradas. La extensión M1/M2 añade las migraciones
`004_e3_h1_dispatcher_claims.sql` y `005_e3_h1_backup.sql`. `002` activa RLS en inbox, conversations, turns,
outcomes y deliveries; el adapter establece deployment/tenant con
`set_config(..., true)` en cada transacción scoped. `003` agrega leases por
recurso con tiempo de BD y generación monotónica; el commit exige claims de
evento y conversación vigentes. La campaña posterior a M1 aplicó también
`004`/`005`/`006` y pasó 8 tests Neon en la campaña integrada final: conexiones y roles, ausencia de scope,
aislamiento de dos tenants en conexión reutilizada, replay/commit, rollback
ante revisión obsoleta, competencia de dos procesos, expiración/takeover,
fencing obsoleto y ownership global del dispatcher. Los fixtures de datos se
borraron al terminar. La prueba M2 con filas sintéticas exportó, eliminó y
restauró una fila por tabla; el segundo import fue idempotente y se observaron
RPO/RTO de 1.60/4.96 s y 9.94/4.32 s. La evidencia sanitizada está en
`evals/results/e3-h1-m2-neon-2026-10-10.json`.

El esquema de bindings/memberships y su resolución previa al scope pertenecen a
E3-06/Identity conforme ADR-008; no están implementados en este slice. E3-04
y E3-05 tienen evidencia en la campaña final y en M2; la equivalencia completa
quedó cubierta por la suite dirigida y el smoke Compose. El expediente E3-1
está `ready_for_gate` y conserva `gate_closed=false` hasta la decisión formal.

## Comandos y límites de esta evidencia

Inspección no sensible realizada mediante `npx --yes neon@8.3.3`:

```text
neon projects get dawn-thunder-41457275 --output json
neon branches get e3-h1-synthetic --output json
neon roles list --branch e3-h1-synthetic --output json
```

La inspección de flags de roles se hizo con `uv run --isolated --extra
deployment python scripts/e3/neon_h1.py inspect-roles`; sólo se imprimieron
nombres y flags, nunca DSNs ni contraseñas.

`uv run --isolated --extra deployment python scripts/e3/neon_h1.py prepare`
completó provisioning SQL/grants y escribió el archivo local protegido.
`INCUBIA_E3_NEON_TESTS=1 INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic uv run
--isolated --extra test --extra deployment python scripts/e3/run_neon_h1.py`
ejecutó sólo `tests/integration/neon`: la campaña integrada final reportó 8
pasos correctos después de aplicar `004`/`005`/`006`.
El runner valida la rama
resolviendo el endpoint esperado con Neon CLI; no imprime DSNs. Las escrituras
fueron las migraciones versionadas y fixtures sintéticos transaccionales, que
se limpiaron al terminar.

**Siguiente paso:** revisar el expediente integrado y registrar la decisión
E3-1 antes de la expiración de la rama temporal. No cerrar E3-1 sólo por este
preflight ni por el resultado automático del runner.
