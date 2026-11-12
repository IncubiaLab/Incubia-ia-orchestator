---
tipo: decision
estado: aceptada
fecha: 2026-11-11
---

# Composición ejecutable del orchestrator P1 — decisión

Se adopta la composición productiva unificada para el VPS:

1. **Composition Root (`src/incubia_orchestrator/bootstrap/vps.py`):**
   - Fabrica `VPSSettings` y `VPSService`.
   - Utiliza `PooledConnections` para compartir el pool entre `PostgresLedger` y `PostgresAuditLog`.
   - Inyecta `OpenAILLM` con límites ratificados (`limits.py`) o `FakeLLM` si se solicita modo simulado.
   - Aplica claims atómicos, deduplicación por `idempotency_key`, control de lease y commit conversacional.
2. **Servidor HTTP (`src/incubia_orchestrator/interfaces/http/service.py`):**
   - `DrainingHTTPServer` con `drain_seconds=60.0`.
   - Autenticación Bearer (`>=32` caracteres) con `hmac.compare_digest`.
   - Rutas `/healthz`, `/readyz`, `/metrics`, `POST /v1/executions` y `POST /v1/turns`.
3. **Preservación de baselines anteriores:**
   - `bootstrap/d0.py` y `interfaces/http/main.py` permanecen sin cambios como baseline de prueba local.

[[01-Investigacion/Composicion-P1/Investigacion - composicion ejecutable del orchestrator P1]] · [[Composición ejecutable del orchestrator P1 - beneficios]] · [[Composición ejecutable del orchestrator P1 - contras y riesgos]] · [[03-Implementacion/Composición ejecutable del orchestrator P1 - estado de implementación]]
