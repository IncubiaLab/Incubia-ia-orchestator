# Fuentes y correspondencia con Linear — etapa 3

Fecha: 2026-10-07. Usa el corte documental de [revisión E2](../etapa-2/LINEAR-ADR.md), el [registro ADR local](../../adr/README.md) y los enlaces fuente del SAD. ADR-008 y ADR-010 se revalidaron en Linear y son Accepted; el resto de estados externos debe revalidarse en E3-01 antes de ratificar decisiones o cerrar issues.

## Correspondencia de objetivos

| Fuente / hito de plataforma | Contribución E3 | Condición |
| --- | --- | --- |
| HEC-7 / 02 Authentication & Organizations | H0/H2: identidad y aislamiento | No declarar auth de producción por tener bindings de prueba. |
| HEC-9 / 03 External System Integration | H3: una integración READ | Fixture no cierra conector real. |
| HEC-11/12 / 04 Chatbot Core | H3/H4: ToolExecutor y Retrieval, respuesta combinada | Contratos hexagonales y evidencia E2E. |
| 05 RAG & Knowledge / 06 Conversation & Context | H1/H4: estado Neon y recuperación/documentos | ADR-008 fija Conversation/UoW; ADR-010 fija pgvector y una base de Knowledge por deployment. |
| 07 Lead Capture / 08 Failure → Case | H6: registro interno de lead/case | CRM/helpdesk y envío comercial externos siguen fuera del corte. |
| HEC-14 / 09 Observability & Audit | H5: correlación, métricas, runbooks | Eventos y restore/carga verificados. |
| 10 MVP Validation / 11 Production AI Hardening | H5/H6: aislamiento, calidad y operación | SLO y gate release acreditados. |
| 12 Hybrid & Local / HEC-17, 13 Model Routing | Sin implementación en E3 | No confundir routing de capability con selección de modelo. |

## ADR aplicables

Aceptados en el corte heredado y revalidado: ORCH-001/003/004/005/006/007/008/010 y estrategia IA/Knowledge. Propuestos o backlog: 009/012/013/014/015/017–024. Implementar persistencia/UoW y pgvector conforme a 008/010; resolver memoria, observabilidad, retries y topología durante H0–H5. Mutations y resume requieren sus decisiones específicas. ORCH-025 es una decisión local para Neon, con rollout condicionado; no consta como cerrada en Linear.

[SAD v1.1](https://linear.app/hector-cruz/document/borrador-sad-agente-orquestador-de-ia-mvp-v11-acd47cd9eb13), [proyecto MVP](https://linear.app/hector-cruz/project/incubia-platform-mvp-67f3883cb76e), [registro de ADR](https://linear.app/hector-cruz/document/incubia-mvp-adr-register-3fce75c3bbce).
