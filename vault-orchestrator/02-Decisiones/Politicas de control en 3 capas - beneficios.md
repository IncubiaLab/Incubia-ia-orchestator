---
tipo: decision-beneficios
tema: politicas-control-3-capas
fecha: 2026-11-12
---

# Políticas de control en 3 capas — beneficios

- **Defensa en profundidad real:** Capa 1 bloquea peticiones sensibles antes de gastar tokens o consultar RAG y redacta secretos accidentales en la salida.
- **Cero fuga de Capa 2 al contexto del LLM:** El pre-filtrado en SQL (`PostgresOrbitKnowledgeStore`) impide que chunks `admin_only` entren en la ventana del LLM para usuarios `actor`/`operator`.
- **Modo fail-closed por diseño:** Documentos sin `accessTier` se indexan como `admin_only` y turnos sin `actor.role` se evalúan como `actor`.
- **Trazabilidad:** Cada bloqueo de Capa 1 registra un evento `AuditEventType.POLICY_DECISION` en `PostgresAuditLog` sin guardar secretos ni prompts completos.

Relacionado: [[Investigacion - politicas de control en 3 capas]] · [[Politicas de control en 3 capas - contras y riesgos]] · [[Politicas de control en 3 capas - decisión]] · [[Politicas de control en 3 capas - estado de implementación]]

