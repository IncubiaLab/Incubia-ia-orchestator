# Goals — etapa 3

Estado: propuestos, pendientes de implementación y evidencia. Los umbrales de calidad son criterios de aceptación de este corte; los SLO productivos se ratifican en H0.

| Goal | Resultado medible | Hito / gate |
| --- | --- | --- |
| G1 | Contratos de persistencia/identidad versionados; inventario de E2 y ADR bloqueantes; A/B/C cerrados antes del piloto integrado E3 | H0 / E3-0 |
| G2 | Neon preserva IDs, revisión y claves de deduplicación; duplicados concurrentes producen 1 turno/outcome/outbox; restore medido | H1 / E3-1 |
| G3 | Dos tenants y dos actores por tenant: cero lectura, escritura, discovery o entrega cruzada; revocación efectiva antes de siguiente operación | H2 / E3-2 |
| G4 | Al menos 1 integración externa READ por Tool Layer; DENY/INDETERMINATE/REQUIRE_APPROVAL producen 0 llamadas externas; payload inválido no ejecuta | H3 / E3-3 |
| G5 | Retrieval multi-tenant sobre ≥40 consultas val y ≥20 dev: recall@5 ≥85% en casos respondibles, abstención ≥90% en no respondibles, cero fuga | H4 / E3-4 |
| G6 | ≥24 escenarios de respuesta combinada: ≥85% afirmaciones verificables respaldadas, ≥95% referencias válidas, cero secretos/datos ajenos; rubricado manual | H4/H6 / E3-4/6 |
| G7 | 100% ejecuciones de la campaña tienen IDs y eventos correlacionados de policy/tool/retrieval/outcome; logs sin secretos ni transcripciones por defecto | H5 / E3-5 |
| G8 | Lead con consentimiento y fallback a caso internos: replay genera 1 registro; actor no autorizado no consulta; derivación externa desactivada en primer corte | H6 / E3-6 |
| G9 | Carga y fallos medidos, rollback/restore reproducidos; límite monetario y uso real reconciliados; CLI fake y Telegram conservan contratos | H5/H6 / E3-5/6 |

## Presupuestos y NFR

Propuesta inicial de ingeniería: RPO ≤24 h y RTO ≤1 h ante pérdida de almacenamiento, conservando recuperación sin repetir efectos. La campaña reporta p50/p95/p99 y n de recepción→outcome y recepción→confirmación de entrega; objetivo provisional p95 ≤5 s para consultas simples bajo la carga acordada. Si depende del proveedor y no se cumple, el gate queda abierto hasta ajustar diseño o ratificar un objetivo nuevo con evidencia.

“80 concurrentes” del SAD se desambigua en H0: medir tanto 80 sesiones activas con mensajes espaciados como una ráfaga de 80 solicitudes en vuelo con fakes; declarar RPS y duración. La campaña real usa el presupuesto autorizado y no presume 80 llamadas simultáneas permitidas por el proveedor. Se reportan colas, saturación, rechazo por límites y errores; ninguna pérdida silenciosa ni duplicación lógica.

`eval-e3` registra `max_calls`, `max_output_tokens`, `usd_cap`, deadline y límites por tenant. Ningún valor nulo autoriza gasto; el responsable fija los valores antes de evaluación real. El estimado se reserva durablemente antes de la llamada y se reconcilia con usage/precios fechados. No reiniciar los contadores CLI/E2.

## Definición de terminado

G1–G9 con evidencia fechada, gates E3-0…6 cerrados, decisiones aplicables ratificadas y limitaciones registradas. Una suite fake, una conexión Neon o un smoke de LLM aislado no acreditan calidad ni release productivo.
