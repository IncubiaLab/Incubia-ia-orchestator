# TODOS — Políticas de Control en 3 Capas

Fecha: 2026-11-13
Estado: Implementada y verificada en Orchestrator, Orbit y Neon Knowledge (`incubialab_knowledge_dev`).
Referencias: [GOALS.md](GOALS.md) · [ROADMAP.md](ROADMAP.md) · [DESSIGN.md](DESSIGN.md) · [howto.md](howto.md)

## 1. Definición y contratos de dominio
- [x] Definir `AccessTier` (`workspace_general`, `admin_only`) en `modules/knowledge/domain.py`.
- [x] Crear `modules/governance/domain/guardrails.py` con reglas puras de **Capa 1** (input/output).
- [x] Definir mapeo oficial `Role -> frozenset[AccessTier]` en `governance/domain/` (`ACTOR`/`OPERATOR` -> `{WORKSPACE_GENERAL}`; `ADMIN` -> `{WORKSPACE_GENERAL, ADMIN_ONLY}`).

## 2. Base de datos Knowledge (Neon)
- [x] Verificar último número de migración en `migrations/knowledge/` y crear migración *expand-only* para `access_tier` (`DEFAULT 'admin_only'`): `migrations/knowledge/003_knowledge_access_tier.sql`.
- [x] Validar migración con `tests/unit/test_e3_migration_rollback.py`.
- [x] Actualizar `PostgresOrbitKnowledgeStore` (`postgres_documents.py`) para guardar `access_tier` en `upsert_document` y pre-filtrar `AND s.access_tier = ANY(%s)` en `search_workspace` (`retrieve_workspace`).

## 3. Runtime, HTTP y Política (`service.py`, `vps.py`, `InProcessPolicyEngine`)
- [x] Actualizar `validate_orbit_turn` (`service.py`) para recibir `actor.role` (validado contra `Role`, default *fail-closed* `actor`).
- [x] Actualizar `validate_knowledge_document_payload` (`service.py`) para recibir `document.accessTier` (fail-closed a `admin_only`).
- [x] Conectar `evaluate_capa1_input` antes de RAG/LLM y `sanitize_capa1_output` después del LLM.
- [x] Pasar `role` efectivo a `InProcessPolicyEngine` en `bootstrap/vps.py` y registrar eventos de denegación en `PostgresAuditLog` (`audit_policy_denial`).
- [x] Actualizar instrucciones de sistema en `config/e2/profiles/general.yaml` reforzando Capa 1.

## 4. Integración Orbit + Corpus Drive/Linear
- [x] Coordinar en Orbit (`backend/src/orchestrator/client.ts` y `backend/src/assistant/service.ts`) el envío de `actor.role` desde la sesión autenticada del workspace (`workspace_admin`/`platform_admin` -> `admin`, `secret_admin` -> `operator`, resto -> `actor`).
- [x] Coordinar el envío de `accessTier` en `syncKnowledgeDocument()` (`backend/src/jobs/worker.ts`):
  - Capa 2 (`admin_only`): Requerimientos, NFRs, clientes, legal, info sensible de empresa y documentos sin coincidencia explícita.
  - Capa 3 (`workspace_general`): Linear, manuales de uso, brandbooks, stacks tecnológicos.
- [x] Aplicar `003_knowledge_access_tier.sql` en Neon y ejecutar backfill/re-etiquetado (`scripts/e3/apply_knowledge_access_tier.py --apply`): aplicado y verificado sobre 383 fuentes activas (`workspace_general`: 305, `admin_only`: 78).

## 5. Verificación y documentación
- [x] Escribir tests unitarios de Capa 1 (passwords, secretos, PII, OpenAI interno) para todos los roles (`tests/unit/test_politicas_control_3_capas.py`).
- [x] Escribir tests de pre-filtrado Capa 2 vs Capa 3 (`actor` bloqueado de `admin_only`, `admin` con acceso a Capa 2 y Capa 3, `admin` bloqueado de Capa 1).
- [x] Ejecutar verificación completa (`uv lock --check --offline`, `compileall`, `pytest -q`, `git diff --check`): `536 passed, 10 skipped`.
- [x] Documentar investigación, decisión y estado en `vault-orchestrator/` y actualizar `vault-orchestrator/00-Entrada/Mapa de conocimiento.md`.

