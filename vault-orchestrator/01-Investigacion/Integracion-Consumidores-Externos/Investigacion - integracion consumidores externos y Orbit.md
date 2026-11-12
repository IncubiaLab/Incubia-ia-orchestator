---
tipo: investigacion
tema: Integración consumidores externos y Orbit
estado: completada
fecha: 2026-11-11
---

# Investigación — Integración consumidores externos y Orbit

## Pregunta y alcance

¿Qué contrato HTTP/SSE expone actualmente el AI Orchestrator en el VPS (`src/incubia_orchestrator/interfaces/http/service.py`) para clientes externos desacoplados como Incubia Orbit y futuros consumidores, y qué brechas contractuales deben mantenerse documentadas?

## Contexto observado

- El servidor VPS (`service.py`) implementa:
  - `GET /healthz` (`{"status": "ok"}`) y `GET /readyz` (`200 {"status": "ready"}` o `503 {"status": "not_ready"|"draining"}`)
  - `GET /metrics`
  - `POST /v1/executions` (payload JSON estricto con `conversation_id`, `message` y opcionales `tenant_id`, `actor_id`; cabecera opcional `Idempotency-Key`; respuestas `401`, `400`, `409`, `429` + `Retry-After`, `503`)
  - `POST /v1/turns` (payload JSON estricto con exactamente 8 campos `validate_orbit_turn`: `requestId`, `turnId`, `conversationId`, `workspaceId`, `actor: { id }`, `projectId`, `question`, `evidence`; emite SSE con `event: delta {"text"}`, `event: citation {"resourceId","excerpt"}` y `event: done {"answer","turnId"}`).
- Desde Incubia Orbit se implementó un cliente TypeScript desacoplado sin dependencias de framework (`backend/src/contracts/orchestrator.ts` y `backend/src/orchestrator/client.ts`) reutilizable por otros proyectos, junto con un adaptador Orbit que enriquece los eventos SSE hacia `AssistantPage.tsx` (`turnId`, `conversationId`, `citations[].title`).
- Por el lado de ingesta documental desde workers externos (`ORCHESTRATOR_KNOWLEDGE_PATH=/v1/knowledge/documents`), `service.py` habilita ahora `POST /v1/knowledge/documents` conectado con `PostgresOrbitKnowledgeStore` (roles separados `incubia_kb_ingestor` e `incubia_kb_runtime` sobre `incubialab_knowledge_dev`), extracción `.txt`/`.md`/`.csv`/`.pdf`/`.docx`, guardas SSRF HTTPS y recuperación RAG por `workspaceId` dentro de `POST /v1/turns`.

## Hallazgos y fuentes primarias

- `validate_orbit_turn` (`service.py`) compara `set(body) != fields` y `set(actor) != {"id"}`; los clientes externos reutilizables deben serializar únicamente las claves exactas del contrato para evitar rechazos `400 invalid_request`.
- `POST /v1/turns` emite las citas como eventos `citation` individuales y omite el arreglo `citations` dentro del evento `done`; los consumidores UI que leen `done.citations` necesitan que el cliente o el BFF acumule y normalice esas citas sin acoplar cambios en el servidor hasta una revisión de versión del protocolo.
- La conexión desde clientes externos por HTTPS detrás de Caddy (`https://agent-staging.incubialab.com`) quedó verificada de extremo a extremo contra `OrchestratorClient` compilado, incluyendo `/healthz`, `/readyz`, rechazo `401`, ejecución idempotente con replay en `/v1/executions` y streaming SSE con extracción de cita sobre evidencia sintética en `/v1/turns`.

## Alternativas evaluadas

1. **Adaptar únicamente el endpoint del servidor VPS para emular el payload UI de Orbit:** rechazado; acoplaría la API del Orchestrator a un consumidor concreto en lugar de mantener un contrato SSE estable y limpio.
2. **Mantener estable el contrato del servidor VPS y proveer un cliente SDK agnóstico con normalización en cada BFF consumidor:** elegida; conserva la estabilidad de `service.py` para múltiples consumidores y aisla las adaptaciones de UI dentro de cada aplicación.

## Recomendación

Conservar los contratos HTTP/SSE actuales del servidor VPS (`/v1/executions`, `/v1/turns`, `/v1/knowledge/documents`, `/healthz`, `/readyz`, `/metrics`) como interfaz pública para consumidores autenticados vía `Bearer`, manteniendo la separación de roles de Knowledge (`ADR-ORCH-010`), validación estricta de payloads y protección SSRF en descargas documentales.

## Beneficios

Enlazar: [[Integración consumidores externos y Orbit - beneficios]]

## Contras y riesgos

Enlazar: [[Integración consumidores externos y Orbit - contras y riesgos]]

## Decisión

Enlazar: [[Integración consumidores externos y Orbit - decisión]]

## Estado de implementación

Enlazar: [[Integración consumidores externos y Orbit - estado de implementación]]

