# Persistencia y RAG en Neon — contras y riesgos

Fecha: 2026-11-11.

- **Ramas efímeras y expiración en desarrollo:** la rama sintética `e3-h1-synthetic` y las ramas de prueba tienen TTL y ventana PITR acotada; requieren recreación y reprovisioning con `neon_h1.py` si expiran.
- **Cobertura parcial de backup actual:** `scripts/e3/h1_backup.py` exporta y restaura las tablas del ledger conversacional (`001`–`006`), pero aún requiere extender el procedimiento de restore a `audit_events` (`008`) y a la base Knowledge por deployment (`ADR-ORCH-024`).
- **Granularidad actual de chunks e ingesta Drive (`TODOS.md`):** el esquema actual publica cada chunk como fuente individual (`drive:<id>:<n>`), exporta únicamente Google Docs a Markdown y aún tiene pendiente el filtrado de ACL por documento antes del `top-k`.
- **Diferencia entre RAG de IncubiaLab y Knowledge de Orbit:** Orbit gestiona sus propios documentos originales en el bucket privado `incubia-knowledge` y envía evidencia ya autorizada por el BFF al gateway, mientras que el módulo `knowledge` del orchestrator gestiona el corpus por deployment (IncubiaLab). Ambos contratos no deben confundirse.

[[01-Investigacion/Persistencia-y-RAG-Neon/Investigacion - persistencia y RAG en Neon]] · [[Persistencia y RAG en Neon - beneficios]] · [[Persistencia y RAG en Neon - decisión]] · [[03-Implementacion/Persistencia y RAG en Neon - estado de implementación]]
