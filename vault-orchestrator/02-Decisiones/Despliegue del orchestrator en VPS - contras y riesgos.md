# Despliegue del orchestrator en VPS — contras y riesgos

Fecha: 2026-11-11.

- Una sola instancia en VPS no ofrece alta disponibilidad automática: un reinicio del host o contenedor implica indisponibilidad breve hasta que `restart: unless-stopped` recupere el proceso (RTO objetivo `<= 1 h`).
- Los entrypoints actuales están fragmentados: `interfaces/http/main.py` (D0) tiene `PostgresLedger` y `PostgresAuditLog` pero usa `FakeLLM` sin auth, mientras que `interfaces/http/orbit_gateway.py` tiene Bearer auth y `OpenAILLM` pero carece de ledger, auditoría y retrieval Knowledge.
- `requirements.lock` no incluye `psycopg[binary]` ni `psycopg_pool`, lo que impide importar `PooledConnections` dentro de una imagen construida solo con ese lockfile.
- `MonthlyCallLimiter` (20 llamadas/mes, 10 s de espera) y `REAL_MAX_OUTPUT_TOKENS = 128` están cableados en `bootstrap/composition.py` y bloquearían tráfico multiusuario real si no se separan por configuración operativa.
- `http.server` (`DrainingHTTPServer`) requiere proxy HTTPS frontal con límites estrictos de conexión/body/timeout y alinear `drain_seconds` (`10 s`) con el timeout del proveedor LLM (`30–60 s`).

[[01-Investigacion/Despliegue-VPS/Investigacion - despliegue del orchestrator en VPS]] · [[Despliegue del orchestrator en VPS - beneficios]] · [[Despliegue del orchestrator en VPS - decisión]] · [[03-Implementacion/Despliegue del orchestrator en VPS - estado de implementación]]
