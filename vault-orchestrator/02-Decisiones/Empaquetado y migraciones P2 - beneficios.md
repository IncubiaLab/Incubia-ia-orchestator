# Empaquetado y migraciones P2 — beneficios

Fecha: 2026-11-11.

- **Eliminación del bloqueo de dependencias:** `psycopg_pool` garantizado en la imagen, permitiendo arranque seguro de `PooledConnections` en contenedores.
- **Cadena de migraciones íntegra (`001`–`008`):** Asegura que todas las políticas RLS, claims, fencing y la tabla de auditoría durable G7 (`audit_events`) queden provisionadas antes de admitir tráfico.
- **Validación fail-closed de roles:** Evita que un operador intente migrar con credenciales de runtime (`incubia_runtime`).
- **Seguridad en contenedor:** Ejecución como UID/GID `10001:10001`, `/data` preparado y verificación de build/imports automatizada en CI.

[[01-Investigacion/Empaquetado-P2/Investigacion - empaquetado reproducible y cadena completa de migraciones P2]] · [[Empaquetado y migraciones P2 - contras y riesgos]] · [[Empaquetado y migraciones P2 - decisión]] · [[03-Implementacion/Empaquetado y migraciones P2 - estado de implementación]]
