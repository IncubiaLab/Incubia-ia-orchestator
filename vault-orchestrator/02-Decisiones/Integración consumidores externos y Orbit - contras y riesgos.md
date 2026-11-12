---
tipo: contras-y-riesgos
tema: Integración consumidores externos y Orbit
estado: aceptado
fecha: 2026-11-11
---

# Integración consumidores externos y Orbit — contras y riesgos

- **Asimetría de citas SSE en `/v1/turns`:** el servidor emite `event: citation` y un `event: done` sin `citations[]`, por lo que cualquier consumidor nuevo debe acumular citas desde el stream (ya resuelto dentro de `OrchestratorClient.streamTurn()`).
- **Dependencia de URLs firmadas HTTPS públicas en `/v1/knowledge/documents`:** `HttpxDocumentDownloader` bloquea HTTP plano, direcciones loopback y redes privadas por defecto (`INCUBIA_ALLOW_INSECURE_DOWNLOAD_URLS=0`); los consumidores deben emitir URLs HTTPS públicas válidas y con `sizeBytes` exacto dentro de la ventana firmada (180 s en Orbit).
- **Validación estricta de claves JSON en `validate_orbit_turn`, `validate_executions_payload` y `validate_knowledge_document_payload`:** enviar campos adicionales genera `400 invalid_request`; futuras evoluciones requerirán versionado de contrato o campos opcionales explícitos.

## Enlaces

- Investigación: [[Investigacion - integracion consumidores externos y Orbit]]
- Decisión: [[Integración consumidores externos y Orbit - decisión]]

