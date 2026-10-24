# ADR-ORCH-015 — Política de timeouts y reintentos

**Estado:** Propuesto — pendiente de ratificación en el registro de ADRs  
**Fecha:** 2026-10-23  
**Alcance:** LLM, Tool READ, embeddings, ledger y canal de salida; gate E3-5  
**Relacionados:** ADR-ORCH-013 (LLMPort), ADR-ORCH-005, ADR-ORCH-025

## Contexto

ADR-ORCH-025 lista ADR-ORCH-015 como no cerrado. Existen límites dispersos en
código; esta propuesta los unifica y fija la regla que no debe romperse:
**un efecto externo de resultado incierto nunca se reintenta automáticamente.**

## Decisión propuesta

| Frontera | Límite vigente | Política |
| --- | --- | --- |
| Workflow grounded (`grounded_workflow.py`) | `deadline_seconds=10` total | El deadline se propaga al Tool y a retrieval; vencido, abstención |
| Tool READ (`catalog_http.py`, `openfoodfacts.py`) | `timeout_seconds=3`, `total_deadline_seconds=10`, `max_attempts<=2` | Reintento sólo ante timeout, error de transporte, 429/5xx y dentro del deadline; 401/403/4xx no se reintentan |
| LLM (`openai_adapter.py`) | `timeout=30`, `retries=0` por defecto | Reintento opt-in sólo para timeout/transporte/429/5xx; 401 no se reintenta; hoy todo 429 se reintenta antes de inspeccionar `insufficient_quota` (hallazgo: debería clasificarse primero); falla = `FailedExecution` y el inbox vuelve a RECEIVED |
| Embeddings (`openai_embedding.py`) | cliente `timeout=10`, sin reintentos | Falla rápida con `RuntimeError` genérico; la reserva de presupuesto se conserva (fail-closed) |
| Ledger PostgreSQL y audit | `connect_timeout=3`; pool Knowledge `timeout=3` | Rechazo rápido ante saturación; sin cola indefinida |
| Entrega a canal (Telegram) | `SENDING` → `UNKNOWN_EFFECT` si el resultado es incierto | **Sin reintento** en `SENDING`/`UNKNOWN_EFFECT`; un fallo conocido se marca `FAILED` (con `next_attempt_at` en `RATE_LIMIT`); la reprogramación automática de `FAILED` aún no está implementada en el dispatcher (hallazgo abierto) |

Los reintentos de la ejecución completa son a nivel de inbox: una ejecución
con claim vencido vuelve a RECEIVED y la reanuda otro worker con fencing; el
commit conversacional es atómico, por lo que un reintento no duplica turno ni
entrega.

## Consecuencias

- Las operaciones READ y de generación pueden repetirse sin efecto externo;
  el envío no. La única vía para resolver `UNKNOWN_EFFECT` es reconciliación
  manual/operativa.
- Pendiente de decisión: si un fallo de embeddings debe degradar a evidencia
  solo-Tool en vez de propagar error (ver `tests/integration/test_e3_faults.py`).

## Evidencia pendiente para ratificar

- `tests/integration/test_e3_faults.py` y `test_e3_shutdown.py` verdes.
- Campaña con proveedor lento/caído real: tiempo acotado y cero duplicados.
