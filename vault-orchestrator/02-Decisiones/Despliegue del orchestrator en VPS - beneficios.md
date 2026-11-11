# Despliegue del orchestrator en VPS — beneficios

Fecha: 2026-11-11.

- Ejecuta el **orchestrator completo** (runtime LangGraph, políticas, ledger conversacional, auditoría G7, tools READ y retrieval Knowledge) en el VPS, sin depender del PC de desarrollo.
- Mantiene una superficie operativa mínima (Opción A de `ADR-ORCH-024`: una imagen inmutable por digest, un servicio principal y jobs one-shot de migración/ingesta) con costo predecible.
- Aprovecha el aislamiento transaccional RLS y el connection pooling de Neon (`incubia_runtime` / `incubia_kb_runtime`) sin administrar PostgreSQL en el VPS.
- Conserva una ruta directa de escalado horizontal a N réplicas (Opción B de `ADR-ORCH-024`) gracias al diseño de leases y fencing (`003`–`006`) ya verificado en E3-1.
- Permite que Orbit (API/BFF y worker en VPS) y otros aplicativos consuman el orchestrator mediante contratos HTTP autenticados de servidor a servidor.

[[01-Investigacion/Despliegue-VPS/Investigacion - despliegue del orchestrator en VPS]] · [[Despliegue del orchestrator en VPS - contras y riesgos]] · [[Despliegue del orchestrator en VPS - decisión]] · [[03-Implementacion/Despliegue del orchestrator en VPS - estado de implementación]]
