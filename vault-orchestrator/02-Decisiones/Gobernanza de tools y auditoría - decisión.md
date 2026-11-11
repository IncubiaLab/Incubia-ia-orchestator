---
tipo: decision
estado: aceptada
fecha: 2026-11-11
---

# Gobernanza de tools y auditoría — decisión

Decisiones aceptadas por el responsable el 2026-10-23 (`ADR-ORCH-014`, `ADR-ORCH-015`, `ADR-ORCH-026`, gate `E3-3` cerrado):

1. **Solo herramientas `READ` gobernadas por PEP en Etapa 3:** ninguna herramienta de mutación externa se habilita sin nuevo gate; toda invocación requiere política `ALLOW`, credencial activa, allowlist de red y registro previo en `PostgresAuditLog`.
2. **Auditoría durable obligatoria (`ADR-ORCH-014`):** correlación completa por `execution_id` (`policy`, `tool`, `retrieval`, `outcome`) en PostgreSQL bajo RLS, sin secretos ni payloads crudos sensibles.
3. **Política de reintentos y límites (`ADR-ORCH-015`):** cero reintentos ante `PROVIDER_QUOTA` o estados `UNKNOWN_EFFECT`; límites y SLO (`p95 <= 5 s`, `RPO <= 12 h`, `RTO <= 1 h`) ratificados en `config/e3/limits.example.yaml`.

[[01-Investigacion/Gobernanza-tools-y-auditoria/Investigacion - gobernanza de tools y auditoría]] · [[Gobernanza de tools y auditoría - beneficios]] · [[Gobernanza de tools y auditoría - contras y riesgos]] · [[03-Implementacion/Gobernanza de tools y auditoría - estado de implementación]]
