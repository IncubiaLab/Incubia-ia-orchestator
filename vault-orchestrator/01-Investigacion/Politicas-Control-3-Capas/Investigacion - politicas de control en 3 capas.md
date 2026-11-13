---
tipo: investigacion
tema: politicas-control-3-capas
estado: implementada-core-pendiente-orbit-y-backfill
fecha: 2026-11-12
---

# Investigación — Políticas de control en 3 capas (Seguridad, RBAC y Pre-filtrado RAG)

## Pregunta y alcance
¿Cómo implementar un control de acceso y seguridad en 3 capas sobre el orchestrator VPS (`POST /v1/turns`, `POST /v1/knowledge/documents`, `InProcessPolicyEngine` y `PostgresOrbitKnowledgeStore`) que bloquee secretos/PII/OpenAI interno para todos los roles, restrinja información de clientes/requerimientos/legal a `Role.ADMIN` y habilite Linear/manuales/brandbooks/stacks a miembros del workspace?

## Contexto observado en el código
- `identity_tenant/domain/principal.py` ya definía `Role.ACTOR < Role.OPERATOR < Role.ADMIN` y `role_at_least`.
- `interfaces/http/service.py` (`validate_orbit_turn`) solo aceptaba `actor: {"id"}` sin rol, y `PostgresOrbitKnowledgeStore.retrieve_workspace` recuperaba chunks sin clasificación de acceso.
- `bootstrap/vps.py` (`LangGraphOrchestrationRuntime.execute`) instanciaba `InProcessPolicyEngine` sin pasar el rol efectivo ni guardas deterministas de entrada/salida.

## Hallazgos y diseño adoptado
1. **Capa 1 (Invariante global — todos los roles):** Guardas deterministas puras en `governance/domain/guardrails.py` (`evaluate_capa1_input` antes de RAG/LLM y `sanitize_capa1_output` antes de responder) + auditoría en `PostgresAuditLog` + refuerzo en `config/e2/profiles/general.yaml`.
2. **Capa 2 y Capa 3 (RBAC acumulativo):** `Role.ADMIN` accede a `workspace_general` + `admin_only`; `Role.ACTOR` y `Role.OPERATOR` acceden solo a `workspace_general`.
3. **Pre-filtrado obligatorio en SQL:** La restricción entre Capa 2 y Capa 3 se ejecuta en `PostgresOrbitKnowledgeStore.retrieve_workspace` (`AND s.access_tier = ANY(%s)`) antes del `LIMIT`, con columna `access_tier` (`DEFAULT 'admin_only'` *fail-closed*) añadida por `migrations/knowledge/003_knowledge_access_tier.sql`.

## Enlaces
- [[Politicas de control en 3 capas - beneficios]]
- [[Politicas de control en 3 capas - contras y riesgos]]
- [[Politicas de control en 3 capas - decisión]]
- [[Politicas de control en 3 capas - estado de implementación]]

