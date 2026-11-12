---
tipo: investigacion
tema: Composición ejecutable y contrato HTTP del Orchestrator (P1)
estado: completado
fecha: 2026-11-11
---

# Investigación y Diseño — Composición ejecutable y contrato HTTP del Orchestrator (P1)

## Pregunta y alcance

¿Cómo componer en `bootstrap/` y exponer en `interfaces/http/` un servicio HTTP productivo para el VPS que integre el **orchestrator completo** (`PostgresLedger`, `PostgresAuditLog`, `PooledConnections`, `AdmissionLimiter`, `InProcessPolicyEngine`, `OpenAILLM`/`FakeLLM` con límites operativos y `KnowledgePools`/RAG opcional), atendiendo tanto el contrato canónico (`/v1/executions`) como el flujo SSE de Orbit (`/v1/turns`), de manera autenticada, idempotente, transaccional y con apagado ordenado?

## Contexto observado y Brechas resueltas

Hasta ahora coexistían dos extremos parciales:
1. `interfaces/http/main.py` + `bootstrap/d0.py`:
   - Conectaba `PostgresLedger`, `PostgresAuditLog` y `PooledConnections`, pero estaba limitado a `FakeLLM`, tools fake, identidad sintética fija y sin autenticación Bearer.
2. `interfaces/http/orbit_gateway.py` + `bootstrap/composition.py`:
   - Tenía autenticación Bearer (`>=32` caracteres) y validación de turnos, pero operaba sin persistencia (sin `PostgresLedger`), sin auditoría (`PostgresAuditLog`), pasaba historial vacío `()` y usaba `MonthlyCallLimiter` (límite de prueba de 20 llamadas/mes).

## Especificación de la Composición Unificada (`bootstrap/vps.py` y `interfaces/http/service.py`)

### 1. Modelo de Servicio y Ciclo de Vida
- **Unidad:** Un solo servidor HTTP (`DrainingHTTPServer`) que expone `/healthz`, `/readyz`, `/metrics`, `POST /v1/executions` (JSON) y `POST /v1/turns` (SSE / Streaming).
- **Readiness real:** `/readyz` verifica que `PostgresLedger.ready()` sea `True`, que el pool no esté agotado y que el servidor no haya entrado en fase de drenaje.
- **Drenaje:** `drain_seconds = 60.0`, coordinado con el `timeout` máximo de generación LLM (`<= 60s`).
- **Autenticación:**
  - Token Bearer de servidor a servidor (`INCUBIA_ORCHESTRATOR_TOKEN`, mínimo 32 caracteres) evaluado con `hmac.compare_digest`.
  - El payload de `/v1/executions` o `/v1/turns` no puede autoasignarse `deployment_id` ni permisos arbitrarios sin pasar por el scope validado del canal/BFF.

### 2. Composición de Componentes
- **Persistencia:** `PostgresLedger` sobre Neon con `incubia_runtime` por pooler TLS (`sslmode=require`).
- **Auditoría:** `PostgresAuditLog` fail-closed (RLS por scope).
- **Límites:** `AdmissionLimiter` y cuotas cargadas desde `config/e3/limits.example.yaml` (`load_runtime_limits()`), suprimiendo el `MonthlyCallLimiter` en el modo VPS.
- **Motor de Orquestación:** `LangGraphRuntimeAdapter` con `OpenAILLM` (o `FakeLLM` si `INCUBIA_FAKE_MODE=1`), perfiles de especialidad (`General`, `Ventas`, `Marketing`) y motor de políticas `InProcessPolicyEngine`.
- **Knowledge / Retrieval:** Conexión opcional a `PostgresKnowledge` mediante `compose_incubialab_retrieval` cuando esté configurado el deployment de Knowledge.

## Beneficios
Enlazar: [[Composición ejecutable del orchestrator P1 - beneficios]]

## Contras y riesgos
Enlazar: [[Composición ejecutable del orchestrator P1 - contras y riesgos]]

## Decisión
Enlazar: [[Composición ejecutable del orchestrator P1 - decisión]]

## Estado de implementación
Enlazar: [[Composición ejecutable del orchestrator P1 - estado de implementación]]

