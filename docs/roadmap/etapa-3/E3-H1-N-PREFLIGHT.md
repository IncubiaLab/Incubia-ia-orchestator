# E3-H1-N — preflight de Neon

**Fecha de inspección:** 2026-10-09/10 UTC  
**Estado:** preparación inicial y slice de E3-03 ejecutados en rama sintética. No es evidencia de cierre de E3-1.

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
versiones ya registradas. `002` activa RLS en inbox, conversations, turns,
outcomes y deliveries; el adapter establece deployment/tenant con
`set_config(..., true)` en cada transacción scoped. `003` agrega leases por
recurso con tiempo de BD y generación monotónica; el commit exige claims de
evento y conversación vigentes. El runner opt-in pasó 6 tests: conexiones y
roles, ausencia de scope, aislamiento de dos tenants en conexión reutilizada,
replay/commit, rollback ante revisión obsoleta, competencia de dos procesos,
expiración/takeover y rechazo de un token vencido. Los fixtures de datos se
borraron al terminar.

El esquema de bindings/memberships y su resolución previa al scope pertenecen a
E3-06/Identity conforme ADR-008; no están implementados en este slice. E3-04
queda parcial: falta ownership del consumidor Telegram/dispatcher y escenarios
de `UNKNOWN_EFFECT`. Import/export/restore (E3-05), equivalencia completa de
contrato SQLite/PostgreSQL y gate E3-1 siguen pendientes.

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
ejecutó sólo `tests/integration/neon`: 5 pasaron. El runner valida la rama
resolviendo el endpoint esperado con Neon CLI; no imprime DSNs. Las escrituras
fueron las migraciones versionadas y fixtures sintéticos transaccionales, que
se limpiaron al terminar.

**Siguiente paso:** completar integración de E3-04 con ownership de cuenta y
dispatcher; después E3-05 (import/restore) y equivalencia de contrato completa.
Antes de continuar, volver a comprobar la expiración de la rama temporal. No
cerrar E3-1 con este preflight.
