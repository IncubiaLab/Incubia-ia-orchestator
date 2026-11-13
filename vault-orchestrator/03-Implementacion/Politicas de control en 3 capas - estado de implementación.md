---
tipo: implementacion
tema: politicas-control-3-capas
estado: implementada-y-verificada
fecha: 2026-11-13
---

# Políticas de control en 3 capas — estado de implementación

## Implementado en el repositorio
- `src/incubia_orchestrator/modules/governance/domain/guardrails.py`: `evaluate_capa1_input`, `sanitize_capa1_output`, `allowed_access_tiers_for_role`, `CAPA1_DENIAL_MESSAGE`.
- `src/incubia_orchestrator/modules/knowledge/domain.py` y `ports.py`: `AccessTier` (`workspace_general`, `admin_only`) en `DocumentSyncRequest`, `WorkspaceKnowledgeHit` y `DocumentKnowledgeStorePort`.
- `migrations/knowledge/003_knowledge_access_tier.sql`: migración *expand-only* con `access_tier DEFAULT 'admin_only'`.
- `src/incubia_orchestrator/modules/knowledge/adapters/postgres_documents.py` y `application/document_sync.py`: persistencia de `access_tier` y pre-filtrado SQL `s.access_tier = ANY(%s)` en `retrieve_workspace`.
- `src/incubia_orchestrator/interfaces/http/service.py` y `src/incubia_orchestrator/bootstrap/vps.py`: validación de `actor.role` y `document.accessTier`, bloqueo Capa 1 previo a RAG/LLM en `/v1/turns` y `/v1/executions`, auditoría `audit_policy_denial`, propagación de `actor_role` a `InProcessPolicyEngine` y redacción de salida.
- `config/e2/profiles/general.yaml`: refuerzo de Capa 1 en instrucciones.
- `tests/unit/test_politicas_control_3_capas.py`: 15 pruebas unitarias dedicadas.

## Implementado en Orbit (`Incubia Orbit/backend`)
- `src/contracts/orchestrator.ts` y `src/orchestrator/client.ts`: añadidos `actor.role` y `document.accessTier`.
- `src/assistant/service.ts`: mapeo de rol de sesión Orbit (`workspace_admin`/`platform_admin` -> `admin`, `secret_admin` -> `operator`, resto -> `actor`).
- `src/jobs/worker.ts`: clasificación automática `accessTier` en `indexSyncedResourcesInRag` (`linear` y manuales/brandbooks/stacks -> `workspace_general`; resto *fail-closed* -> `admin_only`).
- Verificación Orbit (`cd backend && npm test && npm run typecheck && npm run build`): 20/20 passed, 0 errores.

## Estado en Neon Knowledge (`incubialab_knowledge_dev`)
- Migración `migrations/knowledge/003_knowledge_access_tier.sql` aplicada y backfill ejecutado con `scripts/e3/apply_knowledge_access_tier.py` (383 fuentes activas: 305 `workspace_general`, 78 `admin_only`).

## Despliegue operativo
- Orchestrator VPS (`https://agent-staging.incubialab.com`) y Orbit Fly.io (`https://incubia-orbit.fly.dev`) actualizados con las políticas de 3 capas.

Relacionado: [[Investigacion - politicas de control en 3 capas]] · [[Politicas de control en 3 capas - beneficios]] · [[Politicas de control en 3 capas - contras y riesgos]] · [[Politicas de control en 3 capas - decisión]]

