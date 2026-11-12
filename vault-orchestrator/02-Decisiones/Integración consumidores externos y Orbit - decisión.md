---
tipo: decision
tema: Integración consumidores externos y Orbit
estado: aceptado
fecha: 2026-11-11
---

# Integración consumidores externos y Orbit — decisión

Se documenta y adopta la frontera contractual estable del AI Orchestrator VPS para consumidores externos (comenzando por Incubia Orbit):

1. Los consumidores se conectan vía HTTPS TLS + `Bearer` (`INCUBIA_ORCHESTRATOR_TOKEN`) mediante un cliente HTTP/SSE desacoplado sin dependencias de aplicación.
2. El servidor del Orchestrator conserva su validación estricta en `service.py` (`/v1/executions`, `/v1/turns`, `/v1/knowledge/documents`, `/healthz`, `/readyz`), delegando la acumulación/enriquecimiento de citas de UI en el cliente SDK y el BFF de cada producto.
3. La ingesta HTTP de Knowledge (`POST /v1/knowledge/documents`) y la recuperación RAG por `workspaceId` en `POST /v1/turns` cumplen la separación de bases y roles de `ADR-ORCH-010` (`incubia_kb_ingestor` DML / `incubia_kb_runtime` `SELECT`), descarga HTTPS con guardas SSRF (`HttpxDocumentDownloader`) y presupuesto acotado fail-closed (`ADR-ORCH-014`/`015`).

## Enlaces

- Investigación: [[Investigacion - integracion consumidores externos y Orbit]]
- Beneficios: [[Integración consumidores externos y Orbit - beneficios]]
- Contras y riesgos: [[Integración consumidores externos y Orbit - contras y riesgos]]
- Estado de implementación: [[Integración consumidores externos y Orbit - estado de implementación]]

