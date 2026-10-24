# Goals — etapa 3

Estado: propuestos, pendientes de implementación y evidencia. Los umbrales de calidad son criterios de aceptación de este corte; los SLO fueron ratificados por el responsable el 2026-10-23 (ver Presupuestos y NFR).

## Baseline paralelo E3-D0

E3-D0 no añade un `G0` ni cambia los objetivos G1–G9: es evidencia previa de deployment local y permanece separado de E3-0. Su salida no cierra H1–H5, no acredita Neon/RLS/pgvector/tooling real/LLM ni, por sí sola, ratifica ADR-024 (aceptado después por el responsable, 2026-10-23).

| Nivel | Resultado medible | Relación con goals/gates |
| --- | --- | --- |
| E3-D0-L | Imagen reproducible no-root, Compose local de instancia única, migración separada y app loopback con health/readiness; tres turnos encadenados, replay y reinicio conservan estado durable sin red a proveedores. | Evidencia local de empaquetado y recuperación básica; no sustituye G2, G3, G4, G5, G6, G7 ni G9. |
| E3-D0-R | Misma imagen/contrato con Neon, pgvector, READ y LLM reales autorizados; gasto, audit y métricas registrados. | Posterior a H1–H4; sus mediciones alimentan, pero no reemplazan, la evidencia de G2–G9 y E3-1…E3-5. |

El contrato D0-L sólo recibe `message` y `conversation_id`; el servidor genera cada `execution_id` y toma `deployment_id`/`tenant_id`/`actor_id` de la configuración sintética. El endpoint sin autenticación se limita a loopback y nunca es un mecanismo de identidad ni de acceso productivo.

| Goal | Resultado medible | Hito / gate |
| --- | --- | --- |
| G1 | Contratos de persistencia/identidad versionados; inventario de E2 y ADR bloqueantes; A/B/C cerrados antes del piloto integrado E3 | H0 / E3-0 |
| G2 | Neon preserva IDs, revisión y claves de deduplicación; duplicados concurrentes producen 1 turno/outcome/outbox; restore medido | H1 / E3-1 |
| G3 | Dos tenants y dos actores por tenant: cero lectura, escritura, discovery o entrega cruzada; revocación efectiva antes de siguiente operación | H2 / E3-2 |
| G4 | Al menos 1 integración externa READ por Tool Layer; DENY/INDETERMINATE/REQUIRE_APPROVAL producen 0 llamadas externas; payload inválido no ejecuta | H3 / E3-3 |
| G5 | Retrieval pgvector aislado por deployment sobre ≥40 consultas val y ≥20 dev: recall@5 ≥85% en casos respondibles, abstención ≥90% en no respondibles, p95 ≤1 s bajo perfil MVP y cero fuga cross-deployment | H4 / E3-4 |
| G6 | ≥24 escenarios de respuesta combinada: ≥85% afirmaciones verificables respaldadas, ≥95% referencias válidas, cero secretos/datos ajenos; rubricado manual | H4/H6 / E3-4/6 |
| G7 | 100% ejecuciones de la campaña tienen IDs y eventos correlacionados de policy/tool/retrieval/outcome; logs sin secretos ni transcripciones por defecto | H5 / E3-5 |
| G8 | Lead con consentimiento y fallback a caso internos: replay genera 1 registro; actor no autorizado no consulta; derivación externa desactivada en primer corte | H6 / E3-6 |
| G9 | Carga y fallos medidos, rollback/restore reproducidos; límite monetario y uso real reconciliados; CLI fake y Telegram conservan contratos | H5/H6 / E3-5/6 |

## Presupuestos y NFR

SLO ratificados por el responsable el 2026-10-23: RPO ≤12 h (antes propuesto en 24 h) y RTO ≤1 h ante pérdida de almacenamiento, conservando recuperación sin repetir efectos; retención y región sin cambios. La campaña reporta p50/p95/p99 y n de recepción→outcome y recepción→confirmación de entrega; objetivo ratificado p95 ≤5 s para consultas simples bajo la carga acordada. Si depende del proveedor y no se cumple, el gate queda abierto hasta ajustar diseño o ratificar un objetivo nuevo con evidencia. La ratificación fija el objetivo; no acredita su cumplimiento, que la campaña integrada E3-5 aún debe medir.

“80 concurrentes” del SAD se desambigua en H0: medir tanto 80 sesiones activas con mensajes espaciados como una ráfaga de 80 solicitudes en vuelo con fakes; declarar RPS y duración. La campaña real usa el presupuesto autorizado y no presume 80 llamadas simultáneas permitidas por el proveedor. Se reportan colas, saturación, rechazo por límites y errores; ninguna pérdida silenciosa ni duplicación lógica.

`eval-e3` registra `max_calls`, `max_output_tokens`, `usd_cap`, deadline y límites por tenant. Ningún valor nulo autoriza gasto; el responsable aprobó el 2026-10-23 los límites de `config/e3/limits.example.yaml` (`status: ratified`) y el presupuesto de Neon y OpenAI para la campaña integrada. El estimado se reserva durablemente antes de la llamada y se reconcilia con usage/precios fechados. No reiniciar los contadores CLI/E2.

## Definición de terminado

G1–G9 con evidencia fechada, gates E3-0…6 cerrados, decisiones aplicables ratificadas y limitaciones registradas. E3-D0-L/R puede aportar evidencia operativa acotada, pero no reemplaza esa definición ni cierra por sí solo un gate H1–H5. Una suite fake, una conexión Neon o un smoke de LLM aislado no acreditan calidad ni release productivo.
