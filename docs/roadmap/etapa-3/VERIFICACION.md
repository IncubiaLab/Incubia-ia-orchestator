# Verificación — etapa 3

Estado: E3-D0-L está acreditado con Compose local. E3-H1-N preparó Neon; E3-03/04/05 pasaron la campaña integrada offline, Compose y Neon sintético. E3-07/08 tienen tooling, fixture HTTP y una fuente READ real Open Food Facts v3. La campaña E3-3 de READ gobernado quedó acreditada y el responsable la cerró el 2026-10-23. La campaña integrada E3-4 acreditó G5 y G6 con Neon y READ real; el responsable aceptó sus condiciones y cerró el gate el 2026-10-23. La campaña M3 pasó offline, Compose y Neon; el runner produjo `ready_for_gate` con `gate_closed=false`. M2 restauró filas e informó RPO/RTO. E3-2 también quedó `ready_for_gate`. Actualización 2026-10-23: el responsable cerró E3-1, E3-2, E3-3 y E3-4 (el registro en Linear lo realiza Codex); SLO (p95 ≤5 s, RPO ≤12 h, RTO ≤1 h), límites de `config/e3/limits.example.yaml` y presupuesto Neon/OpenAI quedaron ratificados; ADR-ORCH-024 está Aceptado. E3-5 tiene expediente en borrador ([abajo](#e3-5--expediente-borrador)) con la campaña integrada pendiente. E3-0, E3-5 y E3-6 permanecen abiertos.

| Gate | Tareas | Goals | Evidencia exigida | Estado |
| --- | --- | --- | --- | --- |
| E3-D0-L | Baseline Docker Compose paralelo | — | Build no-root, preflight/readiness, HTTP loopback, cadena/replay/reinicio durable, shutdown y ausencia de red externa | `passed`: `incubia-e3-d0-final`, 52.569 s; no cierra H1–H5 |
| E3-D0-R | Validación real diferida tras H1–H4 | — | Neon, pgvector, READ y LLM autorizados con presupuesto, audit y métricas separados | No iniciado; no sustituye G2–G9 |
| E3-H1-N | Preparación inicial de Neon | G2/G3/G9 | Rama sintética, roles runtime/migrador, TLS, endpoints pool/direct, grants y runner opt-in | [Preflight](E3-H1-N-PREFLIGHT.md): roles/grants/DSNs protegidos; migraciones `001`–`006` y campaña Neon final 8/8. No es gate ni cierra E3-1 |
| E3-0 | 01/02 + cierre E2 | G1 | A/B/C, contratos, decisiones, SLO/retención/presupuesto/responsables | Pendiente |
| E3-1 | 03/04/05 | G2/G3/G9 | Suite contrato DB, carrera multi-proceso/fencing, migración, aislamiento Neon, restore | [Campaña M3](../../../evals/results/e3-1-campaign-2026-10-13-final.json): offline 27/27, Compose passed, Neon 8/8; `ready_for_gate`; **cerrado por el responsable el 2026-10-23** (Linear a cargo de Codex) |
| E3-2 | 06 | G3 | Dos tenants/dos actores, revocación, roles/RLS/pool y discovery fake | [Campaña E3-2](../../../evals/results/e3-2-campaign-2026-10-15-local.json): local 17/17 y Neon 9/9 passed; `ready_for_gate`; **cerrado por el responsable el 2026-10-23** (Linear a cargo de Codex) |
| E3-3 | 07/08 | G4/G7 | READ real controlada, DENY cero llamadas, output/errores/límites y audit | [Campaña READ gobernada](../../../evals/results/e3-3-campaign-2026-10-24.json): ALLOW `SUCCESS`, cuatro rutas no autorizadas con 0 llamadas y audit correlacionado; **cerrado por el responsable el 2026-10-23** |
| E3-4 | 09/10/11 | G5/G6 | Dataset congelado, métricas retrieval y grounding, índices/revocación/injection y aislamiento real | [G5 Neon integrado](../../../evals/results/e3-4-neon-local-20261024T034222Z.json): recall/abstención 1,00, p95 0,592 s y cero fugas; [G6 Neon + READ real](../../../evals/results/e3-4-g6-neon-local-20261024T034222Z.json): 24 casos, 12/12 afirmaciones, 6/6 referencias y cero fallos críticos. **Condiciones aceptadas y gate cerrado por el responsable el 2026-10-23**. |
| E3-5 | 12/13 | G2/G3/G7/G9 | Tracing/audit, shutdown, carga, fallos, SLO y restore/rollback | [Campaña D0 local](../../../evals/results/e3-ops-local-2026-10-15.md): ráfaga 80, sesiones 80 × 10 min, caída DB y shutdown con replay passed; expediente en borrador en [E3-5](#e3-5--expediente-borrador); campaña integrada y decisión PENDIENTES |
| E3-6 | 14/15 | G1–G9 | Lead/case idempotentes, consentimiento, E2E multicanal, rúbrica real/costo y GO registrado | Pendiente |

## Estrategia

El plan operativo para convertir esta evidencia pendiente en cierre está en
[H1-CIERRE.md](H1-CIERRE.md): M1 (E3-03/04 y ownership), M2 (E3-05
export/import y restore medido) y M3 (campaña integrada y expediente E3-1).

Unitarias offline para invariantes, schemas, policy y presupuesto. Integración con fakes/HTTP simulado para errores y casos de uso. Suite PostgreSQL temporal prueba el contrato compartido con SQLite; suite Neon sintética separada comprueba roles, pooling y condiciones operativas. E2E CLI/Telegram se documenta con scopes sintéticos y red explícita. La carga fake distingue mecánica local del comportamiento LLM remoto.

E3-07/08 (2026-10-15): `tests/unit/test_tool_discovery.py` cubre exclusión por estado/scope/schema, versión y selección estable. `tests/integration/test_read_tool.py` y `tests/integration/test_openfoodfacts_read.py` cubren READ con `httpx.MockTransport`, retry/rate limit, policy deny/approval/indeterminate sin llamada, mutation apagada, credencial revocada, SSRF, JSON/payload grande, respuesta maliciosa marcada como no confiable y audit por intento. Comando reproducible: `.venv/bin/pytest -q`; resultado local: 89 passed, 9 skipped. La lectura real se reproduce con `INCUBIA_E3_READ_REAL=1 .venv/bin/python scripts/e3/run_e3_read_campaign.py`.

El acceso de red se permite únicamente a casos `@pytest.mark.neon` cuando
`INCUBIA_E3_NEON_TESTS=1`, `INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic` y el host
de `DATABASE_URL` termina en `.neon.tech`; el runner además valida el rol,
TLS, pooled/direct y que ambas URLs sean de la misma rama/base. Ninguna otra
prueba pierde su bloqueo de sockets. El preflight de conexiones no reemplaza
las pruebas de contrato, aislamiento RLS con datos, fencing ni restore de
E3-03/04/05.

Pruebas de arquitectura protegen Domain/Application de SDK, SQL y LangGraph; runtime adapta contratos propios. Canarios detectan prompts/secretos/datos de tenant o deployment ajeno en respuestas, eventos y logs. Fallos inyectados alrededor de commit/reserva/envío prueban una incorporación lógica y recuperación incierta.

E3-D0-L se ejecuta de forma aislada con Compose local de instancia única. El puerto HTTP se publica sólo en `127.0.0.1`; el endpoint sin autenticación recibe únicamente `message` y `conversation_id`, y el scope sintético se inyecta por configuración, nunca desde el payload. Cada solicitud recibe un `execution_id` distinto, conserva la conversación solicitada y concluye con un commit durable antes del siguiente turno. Este encadenamiento de turnos reemplaza cualquier interpretación de loop interno ilimitado; monedas, ejes y círculos no generan contenedores ni despliegues propios.

## Evidencia específica E3-D0

| Comprobación | E3-D0-L exigido | E3-D0-R diferido |
| --- | --- | --- |
| Imagen y proceso | `docker compose --env-file deploy/e3-d0.env build` repetible, Python 3.12, multi-stage, usuario no-root, stdout sanitizado y sin secretos en la imagen. `scripts/e3/d0_smoke.sh` reúne la evidencia ejecutable L. | Reutiliza exactamente la imagen/contrato aprobado para L. |
| Preflight | `healthz` acredita proceso vivo; `readyz` falla con PostgreSQL o migraciones ausentes y sólo pasa tras DB, configuración y schema válidos. | DB Neon y pgvector disponibles con rol/configuración autorizados. |
| Loop durable | Tres solicitudes encadenadas comparten `conversation_id`, obtienen `execution_id` nuevos y cubren ramas deterministas distintas; se preservan historial, revisión e IDs. | Repetir con adapters reales bajo presupuesto autorizado. |
| Idempotencia y recuperación | Replay del mismo evento produce un solo turno, outcome y entrega lógica; reinicio de `app` y SIGTERM no borran ni pierden silenciosamente la conversación. | Medir además condiciones reales de proveedores y reconciliar costo/audit. |
| Frontera de red | Prueba/registro demuestra cero red a LLM, Telegram, tools y Neon; payload con identidad/deployment es rechazado. | Evidencia separada de Neon, pgvector, READ y LLM, con allowlist, audit, presupuesto y métricas. |

La evidencia D0-R se registra con proveedor, versión, presupuesto autorizado, IDs correlacionados seudonimizados, auditoría, latencias/costos y alcance de datos sintéticos. Aunque todas sus comprobaciones pasen, no sustituye las campañas y umbrales de G2–G9 ni permite cerrar E3-1…E3-5.

## Informe por gate

Registrar fecha/huso, commit, versiones de contratos/schema/perfil/modelo/adapter, configuración sanitizada y responsable; comando/procedimiento reproducible; dataset/hash/split; n, denominadores, latencias p50/p95/p99; intentos/errores/quota/tokens/costo; IDs correlacionados seudonimizados; límites y fallos críticos; enlace a artifact en evals/results; decisión cerrado/pendiente y motivo.

G5 recall usa fuentes relevantes esperadas por query respondible; abstención usa conjunto sin respuesta. G6 cada afirmación verificable se juzga contra fuentes registradas y cada referencia contra permisos/existencia. Reportar métricas de Knowledge separadas por deployment/generación/perfil y casos críticos aunque el promedio pase.

E3-09/10/11 (2026-10-15): `python3 scripts/e3/build_knowledge_dataset.py` regenera `evals/e3/{sources,retrieval,response_cases}.jsonl` y su manifest SHA-256. `.venv/bin/pytest -q` pasó 94/94 pruebas disponibles, con 9 skips de integración opt-in. Se probaron límites de contratos, filtrado por deployment en fake, shape de embedding, composición extractiva, salida READ gobernada y referencias públicas. Esto no mide recall semántico, abstención, p95, HNSW, Neon/pgvector ni rúbrica manual; ningún umbral G5/G6 está acreditado.

Campaña pgvector E3-4 del 2026-10-15: dos bases y roles temporales en `e3-h1-synthetic`, 30 fuentes sintéticas por deployment, búsqueda exacta sobre 80 val. Recall@5 40/40, abstención 0/40, fugas cross-deployment 0 y p95 6,27 s. El p95 incluye una conexión Neon nueva por consulta, como hace el adapter actual; no representa una medición con pool. Revocación y reingesta idempotente pasaron; limpieza de bases/roles se verificó. Resultado `g5_passed=false`, `g6_assessed=false`, `gate_closed=false`. HNSW, reindex/rollback bajo carga, injection documental y permisos de referencias por actor no están acreditados. El runner y el resultado están en `scripts/e3/run_h4_neon_campaign.py` y `evals/results/e3-4-neon-mechanics-2026-10-15.json`.

Repetición aprobada con `text-embedding-3-small:384:e3-h4-v1`: [resultado](../../../evals/results/e3-4-neon-openai-2026-10-15.json) 85 llamadas, 4 886 tokens, USD 0,00009772 estimados, recall@5 40/40, abstención 0/40, p95 2,00 s y cero fugas. El costo facturado todavía requiere reconciliación. G5 falló; G6 sigue sin rúbrica. `gate_closed=false`.

## E3-5 — expediente (borrador)

Estado: **borrador; gate abierto.** Se registra sólo la evidencia ya existente en el repositorio. Todo lo marcado PENDIENTE no está evidenciado y no debe leerse como cumplido. Fecha del borrador: 2026-10-23.

**Contexto.** Rama `dev/3-tier-2nd-int`, commits `d703322` (drenaje HTTP, shutdown/rollback, CI), `527e802`, `1bb1bbb` (variables/secretos CI) y `35933b5` (audit Postgres, métricas, límites, runner de carga, fallos, ADR). Responsable: hector.cruz@sig.systems (hhce2303), referido como «responsable». Rama Neon `e3-h1-synthetic` recreada el 2026-10-23 desde `feat-knowledge-base` (`br-broad-waterfall-b54l45qj`, endpoint `ep-empty-cake-b5rld909`), expira el 2026-11-06; roles `incubia_runtime`/`incubia_migrator` NOBYPASSRLS. Los límites y el SLO están en `config/e3/limits.example.yaml` (`status: ratified`, p95 5 s, RPO 12 h, RTO 1 h).

| Componente | Evidencia disponible | Fuente | Estado |
| --- | --- | --- | --- |
| Shutdown / drenaje | `DrainingHTTPServer` espera requests en vuelo hasta `drain_seconds=10`; SIGTERM con replay, kill durante PROCESSING (recuperable), reinicio antes del vencimiento de lease, kill durante SENDING → `UNKNOWN_EFFECT` sin reenvío, Telegram reintentado tras reinicio | `tests/integration/test_e3_shutdown.py` (6 pruebas), `d703322` | Cubierto offline/local; no ejecutado bajo carga en la plataforma elegida |
| Rollback de migraciones | Archivos contiguos, expand/contract, backfill previo a NOT NULL, políticas recreadas, idempotencia al reaplicar y procedimiento en RUNBOOK | `tests/unit/test_e3_migration_rollback.py`, RUNBOOK (rollback de imagen por digest N-1; esquema/datos por restore) | Cubierto estáticamente; rollback de imagen N-1 NO ejecutado en entorno real |
| CI | Job offline (`pytest -q` sobre `uv sync --frozen`) y job Neon opt-in (`workflow_dispatch`, entorno `neon-e3`, verifica host `*.neon.tech`) | `.github/workflows/ci.yml`, `d703322`, `527e802` | Definido; no hay resultado de CI enlazado en este borrador |
| Neon sintético | Suite marcada Neon 10/10 pasada el 2026-10-23 sobre la rama recreada | Reportado por el responsable; sin artefacto propio en `evals/results` | Aprobado por declaración; archivar la salida del runner |
| G7 audit durable | `PostgresAuditLog` + migración `008_e3_g7_audit.sql` (RLS por scope, runtime sólo INSERT/SELECT, columnas de identificador acotadas), fail-closed antes de I/O del Tool, eventos de policy/tool/retrieval/outcome por `execution_id`, canario de secretos; prueba Neon dedicada | `tests/unit/test_postgres_audit.py`, `tests/integration/neon/test_g7_audit.py`, `35933b5` | Offline y prueba Neon incluida en la suite 10/10; el 100% de correlación exigido por G7 en la campaña integrada PENDIENTE |
| Métricas | Snapshot con scope, percentiles, pool, costo LLM, rechazos, latencia recepción→outcome/entrega; el exporter que falla no rompe request ni commit; etiquetas sin texto libre ni secretos | `tests/integration/test_e3_metrics_export.py`, `35933b5` | Cubierto offline |
| Límites | Carga fail-closed (nulo/ausente/cero/negativo/texto/bool no autorizan gasto); valores ratificados el 2026-10-23 | `src/incubia_orchestrator/foundation/limits.py`, `tests/unit/test_e3_limits.py`, `config/e3/limits.example.yaml` | Ratificado; el test debe reflejar `status: ratified` y RPO 12 h |
| Fallos | LLM, READ, embeddings, pool agotado/recuperación y claim vencido con 2+ workers (commit y envío exactamente una vez; worker obsoleto no puede commit) | `tests/integration/test_e3_faults.py`, `35933b5` | Offline. En `35933b5` la degradación a abstención con embeddings caídos estaba como `xfail` estricto; el hallazgo sigue abierto y no cuenta como evidencia de degradación |
| Runner de carga | Perfiles constante/ráfaga, destinos remotos autenticados con allowlist; un 200 sin contrato de respuesta cuenta como error | `scripts/e3/load.py`, `tests/unit/test_e3_load.py` | Probado offline |
| Restore M2 | RPO 2,12 s / RTO 4,88 s (primer restore), segundo import idempotente, 0 fallos críticos, una fila por tabla del ledger | [`e3-h1-m2-backup-2026-10-23.json`](../../../evals/results/e3-h1-m2-backup-2026-10-23.json) | Medido con volumen mínimo; cubre sólo tablas del ledger, no audit ni Knowledge |
| Campaña D0 local | Ráfaga 80/80 (p95 3,41 s) y 80 sesiones × 600 s, 800/800 (p95 3,88 s), caída de DB y SIGTERM con replay, con fakes (sin LLM/READ/pgvector reales) | [`e3-ops-local-2026-10-15.md`](../../../evals/results/e3-ops-local-2026-10-15.md) | Evidencia local; no sustituye la campaña integrada |
| Decisión D8 | ADR-ORCH-024 Aceptado (opción A con ruta a B y criterios de escala) | [ADR-024](../../adr/ADR-ORCH-024-DEPLOYMENT-TOPOLOGY.md) | Decidido; su evidencia de ratificación sigue pendiente |

**Comandos reproducibles.** Offline: `PYTHONPATH=src .venv/bin/python -m pytest -q`. Neon: `INCUBIA_E3_NEON_TESTS=1 INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic uv run --isolated --extra test --extra deployment python scripts/e3/run_neon_h1.py` (RUNBOOK).

**PENDIENTE — evidencia de la campaña integrada (no iniciada):**

- [ ] Carga ≥10 min por perfil (ráfaga y sostenido) contra Neon real con rol runtime pooled, con LLM/READ/pgvector autorizados: n, denominadores, RPS, p50/p95/p99, errores, CPU/memoria/conexiones, cero pérdida y duplicados. Debe demostrar p95 ≤5 s o dejar el gate abierto.
- [ ] Fallos bajo carga (proveedores caídos, saturación del pooler, claim vencido con 2+ workers) repetidos contra Neon.
- [ ] SIGTERM bajo carga en la plataforma elegida, con `http_drain_abandoned=0` y reconciliación limpia.
- [ ] Restore con volumen representativo, incluyendo audit y Knowledge (procedimiento aún por definir), con RPO ≤12 h y RTO ≤1 h demostrados, y rollback de imagen N-1 ejecutado.
- [ ] Reconciliación de costo: uso real de OpenAI y Neon contra los estimados y el `usd_cap` (presupuesto aprobado el 2026-10-23).
- [ ] 100% de ejecuciones de la campaña con IDs y eventos correlacionados (G7) y logs sin secretos.
- [ ] Resultado archivado en `evals/results/` y enlace de CI.
- [x] ADR-ORCH-014 y ADR-ORCH-015 aceptados por el responsable (Linear HEC-37, HEC-38).

**Decisión del gate E3-5:** PENDIENTE — `gate_closed=false`. Motivo: falta la campaña integrada. Firma del responsable: PENDIENTE (fecha: ________).

## Comprobaciones documentales

Correspondencia G1–G9 ↔ H0–H6 ↔ E3-01…15, enlaces relativos existentes, anchors y diff sin errores. Verificar que propuestas no se presenten como implementadas y estados Linear sean fechados. La validación documental no cierra gates de producción.

Resultado documental previo del 2026-10-07: 14 documentos, 15 tareas únicas y enlaces relativos/anchors comprobados sin errores; `git diff --check` pasó. E3-D0 añade una pista de evidencia a verificar, no un resultado de producto. No se ejecutó una campaña E3 ni se conectaron proveedores por documentar este baseline.


Actualización E3-4 (2026-10-15): [G5 local en Neon](../../../evals/results/e3-4-neon-local-2026-10-15.json) pasó 40/40 recall, 40/40 abstención, p95 0,6177 s, cero fugas, exact/HNSW y pruebas de revocación/rollback. [G6 técnico](../../../evals/results/e3-4-g6-neon-local-2026-10-15.json) evaluó 24 casos: 12/12 afirmaciones respaldadas, 6/6 referencias del manifiesto y cero fallos críticos; la URL pública READ respondió 200 anónimo. El gate sigue abierto por rúbrica manual sin firma y READ de G6 ejecutada con fixture HTTP. El resultado OpenAI anterior fallido se conserva como historial; el modelo local versionado es el candidato actual.
