# Verificación — etapa 3

Estado: E3-D0-L está acreditado con Compose local. E3-H1-N preparó Neon; E3-03/04/05 pasaron la campaña integrada offline, Compose y Neon sintético. E3-07/08 tienen tooling, fixture HTTP y una fuente READ real Open Food Facts v3; el smoke real pasó, pero la campaña completa E3-3 sigue pendiente. La campaña M3 pasó offline, Compose y Neon; el runner produjo `ready_for_gate` con `gate_closed=false`. M2 restauró filas e informó RPO/RTO. E3-2 también quedó `ready_for_gate`. E3-09/10/11 tienen slice offline y campaña pgvector en dos bases Neon sintéticas; G5 pasó con el modelo local versionado; G6 técnico pasó y falta la firma manual. E3-1 permanece abierto hasta registrar la decisión formal. No se cerró ningún gate arquitectónico; E3-0…E3-6 permanecen pendientes.

| Gate | Tareas | Goals | Evidencia exigida | Estado |
| --- | --- | --- | --- | --- |
| E3-D0-L | Baseline Docker Compose paralelo | — | Build no-root, preflight/readiness, HTTP loopback, cadena/replay/reinicio durable, shutdown y ausencia de red externa | `passed`: `incubia-e3-d0-final`, 52.569 s; no cierra H1–H5 |
| E3-D0-R | Validación real diferida tras H1–H4 | — | Neon, pgvector, READ y LLM autorizados con presupuesto, audit y métricas separados | No iniciado; no sustituye G2–G9 |
| E3-H1-N | Preparación inicial de Neon | G2/G3/G9 | Rama sintética, roles runtime/migrador, TLS, endpoints pool/direct, grants y runner opt-in | [Preflight](E3-H1-N-PREFLIGHT.md): roles/grants/DSNs protegidos; migraciones `001`–`006` y campaña Neon final 8/8. No es gate ni cierra E3-1 |
| E3-0 | 01/02 + cierre E2 | G1 | A/B/C, contratos, decisiones, SLO/retención/presupuesto/responsables | Pendiente |
| E3-1 | 03/04/05 | G2/G3/G9 | Suite contrato DB, carrera multi-proceso/fencing, migración, aislamiento Neon, restore | [Campaña M3](../../../evals/results/e3-1-campaign-2026-10-13-final.json): offline 27/27, Compose passed, Neon 8/8; `ready_for_gate`, decisión E3-1 pendiente |
| E3-2 | 06 | G3 | Dos tenants/dos actores, revocación, roles/RLS/pool y discovery fake | [Campaña E3-2](../../../evals/results/e3-2-campaign-2026-10-15-local.json): local 17/17 y Neon 9/9 passed; `ready_for_gate`, `gate_closed=false` hasta decisión formal |
| E3-3 | 07/08 | G4/G7 | READ real controlada, DENY cero llamadas, output/errores/límites y audit | [Smoke real Open Food Facts](../../../evals/results/e3-3-read-openfoodfacts-2026-10-15.json) passed; campaña completa, presupuesto/operación y decisión de gate pendientes |
| E3-4 | 09/10/11 | G5/G6 | Dataset congelado, métricas retrieval y grounding, índices/revocación/injection y aislamiento real | [G5 local Neon](../../../evals/results/e3-4-neon-local-2026-10-15.json) aprobado; [G6 técnico](../../../evals/results/e3-4-g6-neon-local-2026-10-15.json) aprobado. Falta firma manual y READ real integrado; gate abierto. |
| E3-5 | 12/13 | G2/G3/G7/G9 | Tracing/audit, shutdown, carga, fallos, SLO y restore/rollback | [Campaña D0 local](../../../evals/results/e3-ops-local-2026-10-15.md): ráfaga 80, sesiones 80 × 10 min, caída DB y shutdown con replay passed; integración H3/H4, restore/rollback, SLO y decisión pendientes |
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

## Comprobaciones documentales

Correspondencia G1–G9 ↔ H0–H6 ↔ E3-01…15, enlaces relativos existentes, anchors y diff sin errores. Verificar que propuestas no se presenten como implementadas y estados Linear sean fechados. La validación documental no cierra gates de producción.

Resultado documental previo del 2026-10-07: 14 documentos, 15 tareas únicas y enlaces relativos/anchors comprobados sin errores; `git diff --check` pasó. E3-D0 añade una pista de evidencia a verificar, no un resultado de producto. No se ejecutó una campaña E3 ni se conectaron proveedores por documentar este baseline.


Actualización E3-4 (2026-10-15): [G5 local en Neon](../../../evals/results/e3-4-neon-local-2026-10-15.json) pasó 40/40 recall, 40/40 abstención, p95 0,6177 s, cero fugas, exact/HNSW y pruebas de revocación/rollback. [G6 técnico](../../../evals/results/e3-4-g6-neon-local-2026-10-15.json) evaluó 24 casos: 12/12 afirmaciones respaldadas, 6/6 referencias del manifiesto y cero fallos críticos; la URL pública READ respondió 200 anónimo. El gate sigue abierto por rúbrica manual sin firma y READ de G6 ejecutada con fixture HTTP. El resultado OpenAI anterior fallido se conserva como historial; el modelo local versionado es el candidato actual.
