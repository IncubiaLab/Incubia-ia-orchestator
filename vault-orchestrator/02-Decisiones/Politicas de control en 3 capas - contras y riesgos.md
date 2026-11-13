---
tipo: decision-contras-riesgos
tema: politicas-control-3-capas
fecha: 2026-11-12
---

# Políticas de control en 3 capas — contras y riesgos

- **Dependencia de clasificación en ingesta:** Los 164 documentos existentes en `incubialab_knowledge_dev` quedan por defecto en `admin_only` tras aplicar `003_knowledge_access_tier.sql` hasta ejecutar el backfill/re-etiquetado de Capa 3.
- **Dependencia del BFF de Orbit:** Mientras Orbit no envíe `actor.role` en `POST /v1/turns`, todos los usuarios de Orbit se evalúan como `Role.ACTOR` (solo Capa 3).
- **Falsos positivos/negativos léxicos en Capa 1:** Las expresiones regulares deterministas cubren los vectores directos (passwords, API keys, PII masiva, system prompt/OpenAI interno), pero deben mantenerse calibradas para no bloquear preguntas legítimas de arquitectura.

Relacionado: [[Investigacion - politicas de control en 3 capas]] · [[Politicas de control en 3 capas - beneficios]] · [[Politicas de control en 3 capas - decisión]] · [[Politicas de control en 3 capas - estado de implementación]]

