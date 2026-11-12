---
tipo: implementacion
tema: Integración consumidores externos y Orbit
estado: implementado-y-verificado
fecha: 2026-11-11
---

# Integración consumidores externos y Orbit — estado de implementación

## Estado actual en Orchestrator VPS (`Incubia-ia-orchestator`)

- **Implementado y verificado online en VPS staging (`src/incubia_orchestrator/interfaces/http/service.py` y `bootstrap/vps.py`):**
  - `GET /healthz`, `GET /readyz` (valida Ledger Neon + `incubialab_knowledge_dev` cuando Knowledge está habilitado), `GET /metrics`
  - `POST /v1/executions` (con `Idempotency-Key` y replay persistido en Neon)
  - `POST /v1/turns` (SSE `delta`, `citation`, `done`, con recuperación RAG híbrida por `workspaceId` sobre `PostgresOrbitKnowledgeStore` combinando similitud vectorial cosine y ponderación léxica `ts_rank_cd` con partición `doc_rank <= 2` por documento, inyectando evidencia no confiable en el prompt del LLM y resolviendo citas `[[resource:UUID]]`).
  - `POST /v1/knowledge/documents` (`upsert` / `revoke` con soporte para `downloadUrl`, `content` inline y `contentBase64` hasta 28MB; extracción PDF vía `pypdf`, retención y retorno de `extractedText`, embeddings OpenAI con cuota acotada e intercambio atómico de generaciones en Neon).
  - Tolerancia en runtime para respuestas incompletas de OpenAI por límite de tokens (`PROVIDER_INCOMPLETE`), con cuota elevada a 2000 tokens en VPS para síntesis RAG extensa.

## Estado del primer consumidor externo (`Incubia Orbit`)

- Implementado cliente desacoplado en `Incubia Orbit` (`backend/src/contracts/orchestrator.ts`, `backend/src/orchestrator/client.ts`) y adaptador Orbit (`backend/src/orchestrator/index.ts`, `assistant/service.ts`, `jobs/worker.ts`), desplegado en Fly.io (`incubia-orbit`, `app` + `worker`) apuntando a `https://agent-staging.incubialab.com`.
- **Ingesta y Sincronización RAG Completa (Drive + Linear):**
  - **Google Drive:** Filtrado estricto a Google Docs (`application/vnd.google-apps.document`) y PDFs (`application/pdf`) de texto. 14 documentos indexados en RAG (12 PDFs y 2 Docs). Limpieza de 287 recursos no-documentales obsoletos en `orbit.resource`.
  - **Linear:** Sincronización de 3 proyectos, 17 milestones, 73 ADRs, 20 documentos y 36 issues hacia el índice de conocimiento RAG.
  - **Base de Conocimiento:** 164 documentos distintos, 383 fuentes de conocimiento y 29.199 chunks indexados en Neon `incubialab_knowledge_dev` bajo la generación activa.
  - **Visibilidad:** Ámbito a nivel de workspace (`0c17663c-6407-44ba-92a0-d722d52c7fe6`, `incubia-lab`), permitiendo que todos los miembros del workspace busquen y reciban respuestas contextuales con citas verificadas de Drive y Linear.
- Endurecido `KnowledgePools` (`src/incubia_orchestrator/modules/knowledge/adapters/pool.py`) con `check=ConnectionPool.check_connection`, `max_idle=30.0`, `max_lifetime=300.0` y `prepare_threshold=None` para evitar `503 not_ready` transitorios cuando PgBouncer de Neon cierra conexiones ociosas.
- Verificado de extremo a extremo el 2026-11-12 contra `https://agent-staging.incubialab.com` (incluyendo consultas reales desde `incubia-orbit` en Fly.io):
  - Consulta 1: Proyectos y Milestones de Linear (100% verificado, citas exactas a milestones).
  - Consulta 2: ADR-ORCH-024 y decisiones de arquitectura (100% verificado, citas exactas a issues y documentos ADR de Linear).
  - Consulta 3: Acta de Reunión ACT-001 de Incubia Lab y PDFs de Google Drive (100% verificado, citas exactas al PDF en Drive).

## Enlaces

- Investigación: [[Investigacion - integracion consumidores externos y Orbit]]
- Decisión: [[Integración consumidores externos y Orbit - decisión]]
- Rollout VPS P4-P5: [[Rollout y validación VPS P4-P5 - estado de implementación]]

