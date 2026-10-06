# Spec 07 — Contextos y capacidades posteriores

Estas carpetas pertenecen a la estructura objetivo. Se crean e implementan al abrir el vertical slice correspondiente y al cerrar sus contratos. No están exigidas por el primer mensaje HTTP.

| Contexto o capacidad | Ubicación objetivo | Responsabilidad y condición de entrada |
| --- | --- | --- |
| Conversation | `modules/conversation/{domain,application,ports,adapters}` | Conversación canónica y repositorio; estado independiente de GraphState. Definir persistencia y retención antes de implementarla. |
| Identity & Tenant | `modules/identity_tenant/{domain,application,ports,adapters}` | Resolver deployment, tenant, actor, roles, permisos y scopes confiables; probar aislamiento entre organizaciones. |
| Knowledge | `modules/knowledge/{domain,application,ports,adapters}` | Puertos de búsqueda documental y datos estructurados; pgvector/Qdrant solo detrás de adapters y cuando la estrategia RAG se decida. |
| Sales | `modules/sales/` | Información comercial, pricing, leads y handoff comercial. |
| Support | `modules/support/` | Soporte, troubleshooting y escalamiento humano. |
| Reporting | `modules/reporting/` | Consultas estructuradas, métricas y análisis. |
| Audit | `modules/audit/` | Eventos de producto, correlación, consultas sensibles y trazabilidad independientes del runtime. |

## Puertos pendientes

[HEC-11](https://linear.app/hector-cruz/issue/HEC-11/definir-puertos-de-ia-alineados-con-hexagonal-ddd) solicita `RetrievalPort`, `EmbeddingPort`, `KnowledgeRepositoryPort`, `ConversationMemoryPort` y `ToolExecutionPort`. Antes de crearlos se define su dueño por contexto, entrada/salida, errores, timeout y metadata. No se colocan todos automáticamente en `orchestration/ports/`: knowledge, conversation y otros contextos conservan sus contratos propios.

## Decisiones aún abiertas

Revisión del 2026-10-06: routing por capacidades (ADR-ORCH-003), agent/tool registries (004/005) y policy engine (006) ya están aceptados en el [registro de ADRs](https://linear.app/hector-cruz/document/incubia-mvp-adr-register-3fce75c3bbce). Persistencia, memoria, RAG, handoff, intervención humana, observabilidad y fallbacks conservan decisiones abiertas. La [etapa 2](../roadmap/etapa-2/ROADMAP.md) propone un corte de especialistas, contexto y adaptador Telegram; su [revisión de fuentes](../roadmap/etapa-2/LINEAR-ADR.md) distingue propuestas locales de ADR ratificados. Cualquier tool que modifique sistemas externos requiere autorización explícita; las operaciones de mutación permanecen deshabilitadas por defecto en el MVP.

## Fuente

[SAD v1.1](https://linear.app/hector-cruz/document/borrador-sad-agente-orquestador-de-ia-mvp-v11-acd47cd9eb13), [borrador de estructura](https://linear.app/hector-cruz/document/draft-estructura-del-repositorio-incubia-ai-orchestrator-084204cfd1bf), [registro de ADRs](https://linear.app/hector-cruz/document/incubia-mvp-adr-register-3fce75c3bbce).
