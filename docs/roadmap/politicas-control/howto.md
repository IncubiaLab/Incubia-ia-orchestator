# How-to — Implementación de Políticas de Control en 3 Capas

Fecha: 2026-11-12
Relacionado: [GOALS.md](GOALS.md) · [ROADMAP.md](ROADMAP.md) · [DESSIGN.md](DESSIGN.md) · [TODOS.md](TODOS.md)

## 1. Baseline antes de tocar código

Ejecutar desde la raíz del repositorio para confirmar estado limpio:

```bash
uv lock --check --offline
uv run --frozen python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python -m pytest tests/test_boundaries.py tests/unit/test_e3_migration_rollback.py -q
git diff --check
```

## 2. Paso a paso de implementación

### Paso 1 — Dominio de Capa 1 y `AccessTier` (Offline, puro)
1. En `src/incubia_orchestrator/modules/knowledge/domain.py`:
   - Definir `AccessTier(StrEnum)` con `WORKSPACE_GENERAL = "workspace_general"` (Capa 3) y `ADMIN_ONLY = "admin_only"` (Capa 2).
   - Añadir `access_tier: AccessTier = AccessTier.ADMIN_ONLY` a `DocumentSyncRequest` y `WorkspaceKnowledgeHit`.
2. En `src/incubia_orchestrator/modules/governance/domain/`:
   - Crear `guardrails.py` con funciones puras `evaluate_capa1_input(text: str) -> GuardDecision` y `sanitize_capa1_output(text: str) -> GuardDecision`.
   - Cubrir detección de: solicitud de contraseñas/tokens/API keys, PII de otros usuarios, extracción de system prompt y configuración interna de OpenAI; y en salida, redacción de `sk-*`, `npg_*`, DSNs y cabeceras `Bearer`.

### Paso 2 — Migración *expand-only* en `migrations/knowledge/`
1. Crear nueva migración SQL forward-only (ej. `003_knowledge_access_tier.sql` o siguiente correlativo) que añada `access_tier TEXT NOT NULL DEFAULT 'admin_only'` con `CHECK (access_tier IN ('workspace_general', 'admin_only'))` en `knowledge_sources`.
2. Verificar que pasa `tests/unit/test_e3_migration_rollback.py` (sin `DROP` ni destructivos).

### Paso 3 — Pre-filtrado SQL en `PostgresOrbitKnowledgeStore`
1. En `src/incubia_orchestrator/modules/knowledge/adapters/postgres_documents.py`:
   - Actualizar `upsert_document` para persistir `access_tier`.
   - Actualizar `search_workspace(..., allowed_tiers: frozenset[AccessTier])` para incluir `AND s.access_tier = ANY(%s)` **dentro** de la query vectorial antes de `LIMIT %s`.
   - Si `allowed_tiers` está vacío, devolver `()` sin consultar.

### Paso 4 — Propagación de `actor.role` y enforcement en `service.py` y `vps.py`
1. En `src/incubia_orchestrator/interfaces/http/service.py`:
   - Actualizar `validate_orbit_turn` para aceptar `actor.role` (`actor` | `operator` | `admin`). Mantener compatibilidad transitoria solo si está explícitamente documentada (tratando ausencia como `Role.ACTOR`, nunca como `ADMIN`).
   - En `_handle_turns`:
     1. Ejecutar Capa 1 sobre `body["question"]`; si bloquea, auditar y devolver respuesta controlada de denegación sin llamar a RAG ni LLM.
     2. Mapear `Role` -> `allowed_tiers`: `ADMIN` -> `{WORKSPACE_GENERAL, ADMIN_ONLY}`, `ACTOR`/`OPERATOR` -> `{WORKSPACE_GENERAL}`.
     3. Pasar `allowed_tiers` a `retrieve_workspace_knowledge`.
   - Actualizar `validate_knowledge_document_payload` para aceptar `document.accessTier` (default `admin_only` fail-closed).
2. En `src/incubia_orchestrator/bootstrap/vps.py`:
   - Pasar el `role` real al `InProcessPolicyEngine` y registrar denegaciones en `PostgresAuditLog`.
   - Aplicar `sanitize_capa1_output` sobre el texto final antes de entregar al cliente.

### Paso 5 — Clasificación inicial de documentos y verificación
1. Ejecutar backfill/re-sincronización de documentos existentes en `incubialab_knowledge_dev`:
   - Linear + Manuales + Brandbooks + Stacks -> `workspace_general` (Capa 3).
   - Requerimientos, NFRs, Legal, Clientes, Empresa -> `admin_only` (Capa 2).
2. Ejecutar la suite completa:

```bash
uv lock --check --offline
uv run --frozen python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

