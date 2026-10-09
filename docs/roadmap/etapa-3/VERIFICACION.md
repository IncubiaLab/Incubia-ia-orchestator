# Verificación — etapa 3

Estado: E3-D0-L está implementado, pero su evidencia Compose local aún está pendiente por falta de Docker en este workspace. No se ejecutaron campañas E3 ni se cerró ningún gate arquitectónico; E3-0…E3-6 permanecen pendientes.

| Gate | Tareas | Goals | Evidencia exigida | Estado |
| --- | --- | --- | --- | --- |
| E3-D0-L | Baseline Docker Compose paralelo | — | Build no-root, preflight/readiness, HTTP loopback, cadena/replay/reinicio durable, shutdown y ausencia de red externa | Código y smoke script listos; ejecución Compose pendiente, no cierra H1–H5 |
| E3-D0-R | Validación real diferida tras H1–H4 | — | Neon, pgvector, READ y LLM autorizados con presupuesto, audit y métricas separados | No iniciado; no sustituye G2–G9 |
| E3-0 | 01/02 + cierre E2 | G1 | A/B/C, contratos, decisiones, SLO/retención/presupuesto/responsables | Pendiente |
| E3-1 | 03/04/05 | G2/G3/G9 | Suite contrato DB, carrera multi-proceso/fencing, migración, aislamiento Neon, restore | Pendiente |
| E3-2 | 06 | G3 | Dos tenants/dos actores, revocación, roles/RLS/pool y discovery fake | Pendiente |
| E3-3 | 07/08 | G4/G7 | READ real controlada, DENY cero llamadas, output/errores/límites y audit | Pendiente |
| E3-4 | 09/10/11 | G5/G6 | Dataset congelado, métricas retrieval y grounding, índices/revocación/injection y aislamiento real | Pendiente |
| E3-5 | 12/13 | G2/G3/G7/G9 | Tracing/audit, shutdown, carga, fallos, SLO y restore/rollback | Pendiente |
| E3-6 | 14/15 | G1–G9 | Lead/case idempotentes, consentimiento, E2E multicanal, rúbrica real/costo y GO registrado | Pendiente |

## Estrategia

Unitarias offline para invariantes, schemas, policy y presupuesto. Integración con fakes/HTTP simulado para errores y casos de uso. Suite PostgreSQL temporal prueba el contrato compartido con SQLite; suite Neon sintética separada comprueba roles, pooling y condiciones operativas. E2E CLI/Telegram se documenta con scopes sintéticos y red explícita. La carga fake distingue mecánica local del comportamiento LLM remoto.

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

## Comprobaciones documentales

Correspondencia G1–G9 ↔ H0–H6 ↔ E3-01…15, enlaces relativos existentes, anchors y diff sin errores. Verificar que propuestas no se presenten como implementadas y estados Linear sean fechados. La validación documental no cierra gates de producción.

Resultado documental previo del 2026-10-07: 14 documentos, 15 tareas únicas y enlaces relativos/anchors comprobados sin errores; `git diff --check` pasó. E3-D0 añade una pista de evidencia a verificar, no un resultado de producto. No se ejecutó una campaña E3 ni se conectaron proveedores por documentar este baseline.
