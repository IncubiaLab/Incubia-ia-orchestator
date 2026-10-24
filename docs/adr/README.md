# ADR de Incubia AI Orchestrator

Copias de los ADR de Linear que figuran como **Accepted** o **Proposed** en el [registro de ADRs](https://linear.app/hector-cruz/document/incubia-mvp-adr-register-3fce75c3bbce). Cada archivo conserva su estado de origen y enlaza el documento original. Las copias locales facilitan la planificación; Linear sigue siendo la fuente para cambios de estado.

| ADR | Estado | Tema |
| --- | --- | --- |
| [ORCH-001](ADR-ORCH-001.md) | Accepted | LangGraph como runtime reemplazable |
| [ORCH-003](ADR-ORCH-003.md) | Accepted | Routing por capacidades y DecisionModelPort |
| [ORCH-004](ADR-ORCH-004.md) | Accepted | Agent Registry, Discovery y Selection |
| [ORCH-005](ADR-ORCH-005.md) | Accepted | Tool Registry, Discovery y frontera de ejecución |
| [ORCH-006](ADR-ORCH-006.md) | Accepted | Kernel invariants, Policy Engine y Guardrails |
| [ORCH-007](ADR-ORCH-007.md) | Accepted | Contrato de ejecución independiente |
| [ORCH-008](ADR-ORCH-008-CONVERSATION-STATE-PERSISTENCE.md) | Accepted | Persistencia de Conversation State |
| [ORCH-010](ADR-ORCH-010-RAG-VECTOR-STORE.md) | Accepted | Arquitectura RAG y Vector Store |
| [ORCH-013](ADR-ORCH-013.md) | Accepted | LLMPort |
| [ORCH-014](ADR-ORCH-014-AUDIT.md) | Proposed — pendiente de revisión | Audit trail durable y fail-closed |
| [ORCH-015](ADR-ORCH-015-RETRIES.md) | Proposed — pendiente de revisión | Política de timeouts y reintentos |
| [ORCH-017](ADR-ORCH-017.md) | Proposed | Estructura por módulo y contexto |
| [ORCH-018](ADR-ORCH-018.md) | Accepted | Dependencias y composition root |
| [ORCH-019](ADR-ORCH-019.md) | Accepted | Conversation State y GraphState |
| [ORCH-020](ADR-ORCH-020.md) | Accepted | Tests arquitectónicos y de contrato |
| [ORCH-024](ADR-ORCH-024-DEPLOYMENT-TOPOLOGY.md) | Aceptado (2026-10-23, responsable) | Topología de despliegue Tier 3: opción A con ruta a B |
| [ORCH-025](ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md) | Accepted for Tier 3; rollout gated | PostgreSQL administrado con Neon |
| [ORCH-026](ADR-ORCH-026-CONTEXT-ARTIFACT-CACHE.md) | Proposed | Jerarquía de caché de artefactos de contexto |
| [ORCH-027](ADR-ORCH-027-NEON-ROLE-PROVISIONING.md) | Accepted | Provisionamiento de roles PostgreSQL con RLS en Neon |

La serie general del MVP contiene otros estados, entre ellos «Aceptado provisionalmente». Este índice conserva el estado de origen y alcance: ORCH-025 acepta la elección para Tier 3, con activación productiva condicionada por sus gates; no cambia SQLite para Gate A.

Actualización del 2026-10-07: se incorpora ORCH-025, decisión local de Tier 3 para Neon basada en el SAD y ADR-E2-001. ORCH-008 y ORCH-010 quedaron aceptados en Linear: el primero fija Conversation/UoW y el segundo Neon/PostgreSQL + pgvector con una base por deployment para Knowledge. La [planificación Tier 3](../roadmap/etapa-3/ROADMAP.md) define sus gates. La [revisión de etapa 2](../roadmap/etapa-2/LINEAR-ADR.md) registra el inventario de decisiones Linear y las diferencias con la planificación histórica de etapa 1.

Actualización del 2026-10-23: ORCH-014, ORCH-015 y ORCH-024 son borradores locales del gate E3-5 que aún no figuran en el registro de Linear. El responsable aceptó ORCH-024 (hosting D8, opción A); ORCH-014 y ORCH-015 permanecen Propuestos hasta su revisión. El registro en Linear está pendiente.
