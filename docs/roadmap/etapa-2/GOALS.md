# Objetivos — etapa 2

Estado: propuestos el 2026-10-06; G1–G2 en implementación, G3–G7 pendientes de verificación (H2+ activos).

## Objetivo principal

Atender conversaciones útiles con General, Ventas y Marketing desde CLI y Telegram, con contexto pertinente por capacidad y una frontera multicanal que preserve scope, correlación e idempotencia.

| ID | Objetivo verificable | Evidencia de cierre | Hito |
| --- | --- | --- | --- |
| G1 | Tres perfiles versionados con propósito, capabilities, límites, contexto requerido y salida esperada | Matriz AGENTES materializada, fixtures y validación de configuración; cambiar un perfil sin cambiar grafo ni router. | H1 |
| G2 | Contexto mayor y pertinente, separado por conversación/scope y acotado por presupuesto | Pruebas de continuidad de ≥3 turnos, cambio de especialidad, truncamiento y cero filtraciones en casos de aislamiento. | H1/H3 |
| G3 | Routing por capability y discovery separado de selección y policy | Dataset v2 congelado, ≥80 % de exactitud total y por capability; todos los casos críticos de AMBIGUOUS/UNSUPPORTED y scope correctos. | H2 |
| G4 | Contextualización de respuesta independiente de proveedores de mensajería | Mismo request/outcome por CLI, Telegram simulado y otro canal fake; sin tipos Telegram/LangGraph en contratos, Domain o Application. | H3 |
| G5 | Una entrada duplicada no dispara nueva ejecución ni nueva entrega confirmada | Replay secuencial/concurrente y tras reinicio; misma clave y payload conflictivo rechazado; UNKNOWN_EFFECT sin reenvío automático. | H3/H4 |
| G6 | Primer E2E por Telegram | Tres turnos, cambio de especialista y dos chats aislados; casos de fallo seguro, update repetido y reinicio; evidencia de recepción y respuesta real. | H4 |
| G7 | Calidad, trazabilidad y operación reproducibles | Suite sin red, evaluación real de perfiles, tiempos/tokens/costo cuando estén disponibles, guía de arranque y recuperación sin contenido/secretos en logs. | H5 |

## Evaluación propuesta

Dataset de routing v2: al menos 60 casos de validación, con ≥10 por capability inicial y ≥10 por cada estado AMBIGUOUS/UNSUPPORTED; incluir paráfrasis, continuidad contextual y solicitudes fuera de scope. Separar desarrollo y validación antes de ajustar thresholds. Publicar matriz de confusión y conteos, no solo porcentaje agregado. El fake prueba contrato; la calidad semántica se mide con un adapter real de Decision Model.

Calidad de generación: al menos 12 escenarios, cuatro por perfil, incluyendo dato faltante, continuidad y petición fuera de alcance. Rúbrica de cuatro dimensiones (pertinencia, uso fiel del contexto, utilidad de salida y límites), puntuación 0–2 cada una. Meta propuesta: ≥80 % del puntaje total y cero fallos críticos de aislamiento, permisos inventados o afirmación de acciones externas no ejecutadas. Registrar revisión humana y versiones de perfil/modelo/contexto. Una evaluación pequeña acredita el piloto, no producción.

El objetivo ≤5 s de la plataforma se mantiene como referencia de medición: registrar tiempos de decisión, generación y canal, muestras y condiciones. No afirmar cumplimiento estadístico con tres turnos. H0 fijará el umbral operativo del piloto antes de medirlo, evitando ajustarlo después para aparentar éxito.

## Definición de terminado

G1–G7 con evidencia enlazada en VERIFICACION, gates A/B/C cerrados, CLI sin regresión y límites conocidos documentados. El contexto ampliado requiere revisar el presupuesto real de etapa 1 (128 tokens, dos pares, seis intentos mensuales); este roadmap no lo modifica ni autoriza evadir el contador. Decisión H0: se crea el presupuesto `eval-e2` con su propio archivo de contador (`INCUBIA_EVAL_BUDGET_FILE`): 150 llamadas como tope (~72 necesarias + repeticiones), `max_output_tokens=400` y un tope de costo en USD definido por el responsable del presupuesto antes de E2-12. El cupo CLI de 6 llamadas/mes y 128 tokens no se toca ni se reinicia. Gate C no puede cerrarse sin ese tope de USD registrado.

Dataset de routing v2: `evals/routing-v2.jsonl`, una línea por caso: `{"id","text","history":[...],"expected_status","expected_capability","split":"dev|val","tags":[...]}`. Los umbrales se ajustan solo con `dev`; G3 se mide solo con `val`.
