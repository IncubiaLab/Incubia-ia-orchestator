# ADR-ORCH-027 — Provisionamiento de roles PostgreSQL con RLS en Neon

**Estado:** Accepted — ratificado y registrado en Linear  
**Fecha:** 2026-10-10  
**Alcance:** H1, base de Control Plane en Neon, roles migrador/runtime  
**Fuente de verdad:** [ADR-ORCH-027 en Linear](https://linear.app/hector-cruz/document/adr-orch-027-provisionamiento-de-roles-postgresql-con-rls-en-neon-fbfc8c493213).

## Contexto

E3-H1 necesita dos identidades de base separadas: un migrador con DDL acotado y
un runtime sin ownership ni `BYPASSRLS`. Las políticas RLS son parte del
aislamiento entre tenants; por tanto, un rol runtime que omite RLS invalida el
gate aunque las consultas de la aplicación filtren por tenant.

En la rama sintética `e3-h1-synthetic`, creada desde la rama predeterminada
`production`, `neon roles create` generó `incubia_runtime` e
`incubia_migrator`. Una inspección de `pg_roles` el 2026-10-09 observó en ambos
`CREATEDB`, `CREATEROLE` y `BYPASSRLS`; ninguno es superuser. Una sesión como
`neondb_owner` intentó retirar esos atributos, pero Neon/PostgreSQL devolvió
`InsufficientPrivilege`. Los roles API creados para esta campaña fueron
eliminados antes de recibir grants o usarse en la aplicación.

PostgreSQL documenta que `BYPASSRLS` omite todas las políticas RLS y que los
roles de aplicación deben carecer de ese atributo. En PostgreSQL 18, alterar
ciertos atributos de roles también depende de privilegios/administración del
rol objetivo ([CREATE ROLE](https://www.postgresql.org/docs/18/sql-createrole.html),
[ALTER ROLE](https://www.postgresql.org/docs/18/sql-alterrole.html)).

## Decisión

Neon CLI administra proyecto, ramas, base, endpoints y preflight. Crear las
identidades de aplicación mediante SQL desde una sesión administrativa de la
misma rama, con atributos declarados explícitamente seguros:

```sql
CREATE ROLE incubia_runtime LOGIN NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE incubia_migrator LOGIN NOCREATEDB NOCREATEROLE NOBYPASSRLS;
```

El provisioning genera contraseñas criptográficamente aleatorias localmente,
las aplica sin imprimirlas y las guarda únicamente en `deploy/e3-neon.env`,
ignorado por Git y con modo `0600`. No se usan credenciales de roles creados
por API/CLI. Runtime utiliza conexión pooled con TLS; migraciones usan conexión
directa con TLS. La campaña inicial confirmó atributos no privilegiados,
pertenencia nula a `neondb_owner`, runtime sin `CREATE` en `public`, migrador
con `CREATE` y TLS observado en ambas conexiones cliente→Neon.

Si Neon no permite que `neondb_owner` cree estos roles SQL sin privilegios
excesivos, H1 queda bloqueado hasta escoger otro mecanismo admitido por Neon.
No se propone reemplazar RLS por filtros de aplicación.

## Consecuencias

- Neon CLI permanece como interfaz de administración del proyecto y la rama;
  el provisioning SQL de identidades forma parte del procedimiento operativo.
- La rotación de contraseñas SQL debe tener un procedimiento explícito; no se
  presume que `neon connection-string` pueda revelar passwords creados fuera de
  la API de roles.
- Runtime no posee tablas, no crea objetos, no puede modificar roles ni omitir
  RLS. El migrador crea/posee sus objetos de schema, pero tampoco es superuser,
  `CREATEROLE`, `CREATEDB` ni `BYPASSRLS`.
- Los roles API que se crearon inicialmente para esta campaña se eliminaron
  antes de recibir grants o uso; las credenciales locales corresponden sólo a
  los roles SQL.
- La decisión sólo desbloquea E3-03; no acredita E3-1 ni sustituye pruebas de
  fencing, aislamiento, migración, import o restore.

## Evidencia y seguimiento

- Proyecto Neon: Incubia Lab; rama sintética temporal `e3-h1-synthetic`.
- Observación inicial: `pg_roles` mostró `CREATEDB`, `CREATEROLE`, `BYPASSRLS`
  en los roles CLI; `ALTER ROLE` fue rechazado. Esos roles se eliminaron antes
  de grants/uso.
- Tras ratificación, la preparación SQL creó roles con
  `NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`, aplicó grants mínimos de
  conexión/schema y guardó DSNs en archivo local mode `0600` ignorado por Git.
- El runner opt-in pasó 6 checks: runtime pooled TLS sin DDL, migrador directo
  TLS con DDL de schema, RLS sin scope/aislamiento entre tenants, commit/replay,
  rollback por revisión obsoleta, competencia/takeover de leases y rechazo de
  commit con fencing vencido. Ambos roles carecen de flags privilegiados y
  membresía `neondb_owner`. TLS se midió en libpq cliente; `pg_stat_ssl` del
  backend no representa necesariamente el tramo cliente→proxy.
- E3-03 y el núcleo de E3-04 ya aplicaron migraciones y verificaron RLS/UoW y
  fencing sintéticos. Ownership del consumidor Telegram/dispatcher,
  `UNKNOWN_EFFECT` E2E y E3-05 import/restore siguen pendientes; esto no cierra
  E3-1.
