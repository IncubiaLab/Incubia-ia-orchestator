# ADR de Incubia AI Orchestrator

Copias de los ADR de Linear que figuran como **Accepted** o **Proposed** en el [registro de ADRs](https://linear.app/hector-cruz/document/incubia-mvp-adr-register-3fce75c3bbce), consultado el 1 de octubre de 2026. Cada archivo conserva su estado de origen y enlaza el documento original. Las copias locales facilitan la planificación; Linear sigue siendo la fuente para cambios de estado.

| ADR | Estado | Tema |
| --- | --- | --- |
| [ORCH-001](ADR-ORCH-001.md) | Accepted | LangGraph como runtime reemplazable |
| [ORCH-003](ADR-ORCH-003.md) | Accepted | Routing por capacidades y DecisionModelPort |
| [ORCH-004](ADR-ORCH-004.md) | Accepted | Agent Registry, Discovery y Selection |
| [ORCH-005](ADR-ORCH-005.md) | Accepted | Tool Registry, Discovery y frontera de ejecución |
| [ORCH-006](ADR-ORCH-006.md) | Accepted | Kernel invariants, Policy Engine y Guardrails |
| [ORCH-007](ADR-ORCH-007.md) | Accepted | Contrato de ejecución independiente |
| [ORCH-013](ADR-ORCH-013.md) | Proposed | LLMPort |
| [ORCH-017](ADR-ORCH-017.md) | Proposed | Estructura por módulo y contexto |
| [ORCH-018](ADR-ORCH-018.md) | Proposed | Dependencias y composition root |
| [ORCH-019](ADR-ORCH-019.md) | Proposed | Conversation State y GraphState |
| [ORCH-020](ADR-ORCH-020.md) | Proposed | Tests arquitectónicos y de contrato |
| [ORCH-025](ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md) | Accepted for Tier 3; rollout gated | PostgreSQL administrado con Neon |

La serie general del MVP contiene otros estados, entre ellos «Aceptado provisionalmente». Este índice conserva el estado de origen y alcance: ORCH-025 acepta la elección para Tier 3, con activación productiva condicionada por sus gates; no cambia SQLite para Gate A.

Actualización del 2026-10-07: se incorpora ORCH-025, decisión local de Tier 3 para Neon basada en el SAD y ADR-E2-001. La [planificación Tier 3](../roadmap/etapa-3/ROADMAP.md) define sus gates. La [revisión de etapa 2](../roadmap/etapa-2/LINEAR-ADR.md) registra el inventario de decisiones Linear y las diferencias con la planificación histórica de etapa 1.
