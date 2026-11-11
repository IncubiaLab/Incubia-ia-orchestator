# Neon aislado para Knowledge — desarrollo y pruebas

Creado el 2026-10-21 para `feat/knowledge-base`.

| Recurso | Valor |
| --- | --- |
| Proyecto | `dawn-thunder-41457275` |
| Rama | `feat-knowledge-base` |
| Branch ID | `br-still-cell-b5cvn1vh` |
| Padre | `production` / `br-frosty-hall-b5rffy75` |
| Inicialización | `parent-schema`: sólo esquema, sin copiar filas del padre |
| Base del RAG | `incubialab_knowledge_dev`, creada vacía |
| Compute | 0,25 CU, región `aws-us-east-2` |
| Suspensión | Valor predeterminado de cuenta, API `0`; el plan rechazó configurar 300 segundos |
| Expiración | Sin expiración automática; revisar/eliminar al terminar el feature |

Credenciales locales: `deploy/knowledge-neon.env`, permisos `0600`, excluido por `.gitignore`. No cargar este archivo en producción. No se modificaron `.env`, `.neon` ni la configuración de campañas anteriores. Los nombres de variables son configuración explícita del nuevo entorno; los runners existentes no las consumen automáticamente.

- `INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL`: conexión directa, rol `incubia_kb_migrator`, DDL en schema public.
- `INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL`: conexión pooled, rol `incubia_kb_ingestor`, SELECT/INSERT/UPDATE/DELETE sobre tablas futuras creadas por el migrador.
- `INCUBIA_KNOWLEDGE_RUNTIME_DATABASE_URL`: conexión pooled, rol `incubia_kb_runtime`, sólo SELECT sobre esas tablas.

Los tres roles carecen de SUPERUSER/CREATEDB/CREATEROLE/BYPASSRLS. Extensión vector habilitada por el administrador; migraciones Knowledge pendientes. Los grants por defecto se aplican a objetos creados por el migrador, no a objetos creados por otro propietario.

[Preflight sanitizado](../../../evals/results/rag-incubialab/neon-dev-preflight-2026-10-21.json): conexiones, TLS cliente, atributos de roles, DML del ingestor y rechazo de escritura runtime. La tabla sintética de verificación se elimina al finalizar. El TLS se verifica con libpq `ssl_in_use`; `pg_stat_ssl` refleja el tramo backend del proxy y no acredita el cifrado cliente→Neon.

Antes de migrar, comprobar project ID, branch ID y hostname del endpoint contra esta rama; no usar una selección implícita del CLI, cuyo contexto anterior puede apuntar a una rama eliminada. La rama está aislada en datos/cómputo, pero comparte proyecto y facturación. No hay ingestión de Drive ni aceptación RAG-V1 por crear esta infraestructura.

Referencia: [Neon CLI branches](https://neon.com/docs/cli/branches), consultada el 2026-10-21.
