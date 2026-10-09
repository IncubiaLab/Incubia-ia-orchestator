# Verificación — etapa 3

Estado: no se ejecutaron pruebas del producto ni campañas E3. Esta carpeta acredita planificación; los gates técnicos están pendientes.

| Gate | Tareas | Goals | Evidencia exigida | Estado |
| --- | --- | --- | --- | --- |
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

## Informe por gate

Registrar fecha/huso, commit, versiones de contratos/schema/perfil/modelo/adapter, configuración sanitizada y responsable; comando/procedimiento reproducible; dataset/hash/split; n, denominadores, latencias p50/p95/p99; intentos/errores/quota/tokens/costo; IDs correlacionados seudonimizados; límites y fallos críticos; enlace a artifact en evals/results; decisión cerrado/pendiente y motivo.

G5 recall usa fuentes relevantes esperadas por query respondible; abstención usa conjunto sin respuesta. G6 cada afirmación verificable se juzga contra fuentes registradas y cada referencia contra permisos/existencia. Reportar métricas de Knowledge separadas por deployment/generación/perfil y casos críticos aunque el promedio pase.

## Comprobaciones documentales

Correspondencia G1–G9 ↔ H0–H6 ↔ E3-01…15, enlaces relativos existentes, anchors y diff sin errores. Verificar que propuestas no se presenten como implementadas y estados Linear sean fechados. La validación documental no cierra gates de producción.

Resultado documental del 2026-10-07: 14 documentos, 15 tareas únicas y enlaces relativos/anchors comprobados sin errores; `git diff --check` pasó. Se revisó correspondencia G1–G9/H0–H6 y dependencias de identidad/datos/tooling/knowledge. No se ejecutó la suite del producto ni se conectaron proveedores: el cambio es exclusivamente de planificación.
