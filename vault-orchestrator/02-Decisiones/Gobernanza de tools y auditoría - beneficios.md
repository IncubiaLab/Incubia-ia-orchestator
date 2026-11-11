# Gobernanza de tools y auditoría — beneficios

Fecha: 2026-11-11.

- **Cero llamadas en denegación (`DENY`):** el PEP evalúa permisos, estado del descriptor, mutabilidad (`READ`) y vigencia de credenciales antes de abrir cualquier socket.
- **Auditoría *fail-closed* e inmutable en runtime:** si no se puede persistir el evento de auditoría en `audit_events` (bajo RLS y con rol `incubia_runtime` sin permisos de borrado), la herramienta no se ejecuta.
- **Protección contra Prompt Injection y SSRF:** las respuestas de herramientas se encapsulan como evidencia no confiable y los destinos HTTP se validan contra listas permitidas y rangos privados prohibidos.
- **Control estricto de costos y reintentos (`ADR-ORCH-015`):** distingue `PROVIDER_QUOTA` de `PROVIDER_RATE_LIMIT`, evita reintentar efectos no idempotentes (`UNKNOWN_EFFECT`) y bloquea el arranque si `config/e3/limits.example.yaml` no está ratificado.

[[01-Investigacion/Gobernanza-tools-y-auditoria/Investigacion - gobernanza de tools y auditoría]] · [[Gobernanza de tools y auditoría - contras y riesgos]] · [[Gobernanza de tools y auditoría - decisión]] · [[03-Implementacion/Gobernanza de tools y auditoría - estado de implementación]]
