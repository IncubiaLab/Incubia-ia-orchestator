---
tipo: decision
tema: politicas-control-3-capas
estado: aceptada
fecha: 2026-11-12
---

# Políticas de control en 3 capas — decisión

1. Adoptar modelo acumulativo de 3 capas (`Capa 1` bloqueo global para todos los roles; `Capa 2` `admin_only` exclusivo de `Role.ADMIN`; `Capa 3` `workspace_general` para `Role.ACTOR` en adelante).
2. Ubicar las guardas deterministas de Capa 1 en `modules/governance/domain/guardrails.py` y `AccessTier` en `modules/knowledge/domain.py`.
3. Exigir pre-filtrado SQL en `PostgresOrbitKnowledgeStore.retrieve_workspace` mediante la columna `access_tier` añadida por la migración *expand-only* `003_knowledge_access_tier.sql`.
4. Mantener compatibilidad transitoria *fail-closed* en `POST /v1/turns` (`actor.role` ausente -> `actor`) y `POST /v1/knowledge/documents` (`accessTier` ausente -> `admin_only`).

Relacionado: [[Investigacion - politicas de control en 3 capas]] · [[Politicas de control en 3 capas - beneficios]] · [[Politicas de control en 3 capas - contras y riesgos]] · [[Politicas de control en 3 capas - estado de implementación]]

