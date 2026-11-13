# ROADMAP — Políticas de Control en 3 Capas

Fecha: 2026-11-12
Relacionado: [GOALS.md](GOALS.md) · [DESSIGN.md](DESSIGN.md) · [howto.md](howto.md) · [TODOS.md](TODOS.md)

## Fases de ejecución

### Fase 0 — Alineación de contratos y clasificación (Sin cambios destructivos)
- **Objetivo:** Definir taxonomía oficial de sensibilidad (`access_tier` / `classification`), reglas de mapeo Drive/Linear y contrato `actor.role` entre Orbit BFF y Orchestrator.
- **Entregables:**
  - Contrato de dominio en `modules/knowledge/domain.py` y `modules/governance/domain/policy.py`.
  - Regla *fail-closed*: todo documento sin clasificación explícita se trata como `admin_only` (Capa 2).

### Fase 1 — Capa 1: Guardas globales deterministas (Input/Output + Perfil)
- **Objetivo:** Bloquear de raíz preguntas sobre contraseñas, secretos, PII de usuarios e información interna de OpenAI/sistema para **todos los roles**.
- **Entregables:**
  - Módulo puro de evaluación de Capa 1 en `modules/governance/domain/` (reglas deterministas sin dependencias de red/SDK).
  - Integración en `VPSService.execute_turn` / `HandleInbound` antes de invocar RAG o `LLMPort`.
  - Filtro/redacción de salida para patrones de secretos (`sk-`, `npg_`, DSNs, tokens) antes de responder al cliente.
  - Refuerzo de instrucciones en `config/e2/profiles/`.

### Fase 2 — Identidad y RBAC en `POST /v1/turns` y `InProcessPolicyEngine`
- **Objetivo:** Propagar el rol verificado del usuario desde Orbit hasta `InProcessPolicyEngine`.
- **Entregables:**
  - Extensión compatible de `validate_orbit_turn` en `interfaces/http/service.py` para recibir `actor: { id, role }`.
  - Propagación de `role` en `ExecutionScope` o contexto de ejecución hacia `LangGraphOrchestrationRuntime.execute` (`bootstrap/vps.py`) y `InProcessPolicyEngine`.
  - Auditoría de decisiones de política en `PostgresAuditLog`.

### Fase 3 — Capas 2 y 3: Clasificación en ingesta y Pre-filtrado SQL en RAG
- **Objetivo:** Garantizar que `actor` nunca inyecte chunks de Capa 2 en el prompt del LLM.
- **Entregables:**
  - Migración *expand-only* en `migrations/knowledge/` (o metadatos estructurados en `knowledge_sources` / `public_ref` indexado) para persistir `access_tier` (`workspace_general` | `admin_only`).
  - Actualización de `POST /v1/knowledge/documents` (`validate_knowledge_document_payload` y `SyncDocumentKnowledge`).
  - Pre-filtrado SQL en `PostgresOrbitKnowledgeStore.search_workspace` según el rol efectivo del actor.
  - Filtrado espejo de `evidence` entrante en `service.py` si incluye metadatos de visibilidad.

### Fase 4 — Re-clasificación de corpus existente y Verificación E2E
- **Objetivo:** Etiquetar los documentos ya indexados en `incubialab_knowledge_dev` (Drive + Linear) y validar en staging VPS.
- **Entregables:**
  - Script idempotente de clasificación/backfill para fuentes existentes:
    - **Capa 2 (`admin_only`):** Requerimientos, NFRs, documentos de clientes, legal y corporativo de Drive.
    - **Capa 3 (`workspace_general`):** Linear (proyectos, milestones, issues, ADRs), manuales de uso, brandbooks y stacks tecnológicos de Drive.
  - Pruebas unitarias, de frontera (`test_boundaries.py`), integración y smoke test en VPS staging (`test_vps_staging.py` / `test_vps_knowledge.py`).

