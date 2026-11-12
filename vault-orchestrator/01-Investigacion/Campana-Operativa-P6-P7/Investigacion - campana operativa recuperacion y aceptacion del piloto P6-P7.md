---
tipo: investigacion
tema: Campaña operativa recuperación y aceptación del piloto P6-P7
estado: aceptado
fecha: 2026-11-11
---

# Campaña Operativa, Recuperación y Aceptación del Piloto (P6 y P7)

## Pregunta y alcance
¿Cómo acreditar con mediciones verificables y evidencia empírica en el VPS de pruebas los objetivos de nivel de servicio (SLO p95 ≤ 5 s, RPO ≤ 12 h, RTO ≤ 1 h), el drenado graceful ante SIGTERM sin transacciones abandonadas (`http_drain_abandoned=0`), la compatibilidad hacia atrás mediante rollback a la imagen N-1, el procedimiento de restore duradero y la entrega del runbook de operación para la aceptación del piloto (Fases P6 y P7)?

## Contexto observado en el código
- El orchestrator en VPS staging (`agent-staging.incubialab.com`) gestiona la persistencia a través de `PostgresLedger` y `PostgresAuditLog` compartiendo un pool acotado de conexiones Neon (`PooledConnections`) con healthcheck de socket activo (`check=ConnectionPool.check_connection`).
- El servidor `VPSHTTPServer` implementa drenado controlado (`drain_seconds = 60.0`) y responde `503 Service Unavailable` (`{"status":"draining"}`) en `/readyz` ante señales SIGTERM/SIGINT.
- El esquema PostgreSQL (`001`–`008`) se diseñó bajo la directiva *expand/contract*, lo que permite que una imagen previa N-1 (`incubia-orchestrator:e5206c4`) arranque e interactúe sin errores con la base ya migrada.

## Hallazgos verificables
1. **Perfil de Carga Ráfaga (Burst Load):**
   - 2 olas de 4 sesiones concurrentes completadas con 0 errores y 100% éxito HTTP 200.
   - Latencia observada: p50 = 2695.32 ms, **p95 = 3071.56 ms** (cumple holgadamente el SLO p95 ≤ 5000 ms).
2. **Perfil de Carga Sostenida (Sustained Sessions):**
   - 29 peticiones procesadas secuencialmente a través de 3 sesiones concurrentes.
   - 0 errores HTTP, revisiones del ledger estrictamente consistentes (`revisions_consistent = True`), p95 = 3371.70 ms.
3. **Drenado Graceful ante SIGTERM:**
   - Envío de señal SIGTERM al contenedor `orchestrator-staging`.
   - `/readyz` entró inmediatamente en modo fail-closed reportando `503 Service Unavailable` (`status="draining"`).
   - El proceso concluyó las tareas activas y cerró limpiamente conexiones y sockets. Tras reinicio, recuperó su estado `200 READY` sin transacciones incompletas ni bloqueos colgados en Neon.
4. **Rollback N-1 y Compatibilidad Hacia Atrás:**
   - Se configuró la imagen N-1 (`incubia-orchestrator:e5206c4`) en `.env` y se recreó el contenedor.
   - La imagen N-1 arrancó correctamente contra la base de datos migrada, respondiendo `200 OK` en `/healthz` y `/readyz`.
   - El rollforward posterior hacia `incubia-orchestrator:staging` se ejecutó sin fricción.
5. **Verificación de Respaldo y RTO/RPO:**
   - Exportación de paquete scoped mediante `h1_backup.py` en 4.196 s, validando hashes criptográficos de contenido (`content_sha256 = ec408afba...`).
   - RTO medido: < 1 minuto para recreación/recuperación en VPS (< 1 hora SLO).
   - RPO medido: 0 horas (ledger transaccional de escritura adelantada).
6. **Entrega de Runbook Operacional (P7):**
   - Documento `docs/roadmap/etapa-3/RUNBOOK-VPS-OPERACIONAL.md` entregado y verificado.
   - Evidencia archivada en `evals/results/vps/e3-p6-vps-campaign.json`.

## Alternativas evaluadas
- **Pruebas puramente locales (loopback):** Descartadas; no satisfacen los requisitos de gate E3-5 / P6 en entorno VPS real con red pública y proxy Caddy.
- **Rollback destructivo mediante SQL inverso:** Rechazado por `ADR-ORCH-025`; el rollback se sustenta en compatibilidad de imagen N-1 o restore de backup validado.

## Recomendación
Declarar formalmente concluidas y aprobadas las fases P0 a P7 del plan de despliegue en VPS.

## Nodos de convergencia
- Beneficios: [[Campaña operativa y piloto P6-P7 - beneficios]]
- Contras y riesgos: [[Campaña operativa y piloto P6-P7 - contras y riesgos]]
- Decisión: [[Campaña operativa y piloto P6-P7 - decisión]]
- Estado de implementación: [[Campaña operativa y piloto P6-P7 - estado de implementación]]

