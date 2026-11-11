---
tipo: decision
estado: aceptada
fecha: 2026-11-11
---

# Persistencia y RAG en Neon — decisión

Decisiones ratificadas en `ADR-ORCH-008`, `ADR-ORCH-010`, `ADR-ORCH-025` y `ADR-ORCH-027` (gates `E3-1`, `E3-2` y `E3-4` cerrados el 2026-10-23):

1. **Estado conversacional canónico fuera de LangGraph (`ADR-ORCH-008`):** `PostgresLedger` es la única autoridad del historial, turnos, outcomes, inbox/outbox y claims; `GraphState` es efímero por ejecución.
2. **Provisioning SQL sin `BYPASSRLS` (`ADR-ORCH-027`):** el runtime se conecta exclusivamente por endpoint `-pooler` con TLS (`sslmode=require`) usando `incubia_runtime` / `incubia_kb_runtime`; las migraciones y restores usan conexión directa con `incubia_migrator` / `incubia_kb_migrator`.
3. **Vector store en `pgvector` con una base por deployment (`ADR-ORCH-010`):** embeddings de `384` dimensiones (`text-embedding-3-small` o modelo local versionado), consulta acotada por generación activa y composición extractiva/sustentada mediante `GroundedWorkflow`.

[[01-Investigacion/Persistencia-y-RAG-Neon/Investigacion - persistencia y RAG en Neon]] · [[Persistencia y RAG en Neon - beneficios]] · [[Persistencia y RAG en Neon - contras y riesgos]] · [[03-Implementacion/Persistencia y RAG en Neon - estado de implementación]]
