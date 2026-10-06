# Revisión del plan — decisiones y límites

Fecha: 2026-10-06 · Estado: decisiones H0 concretadas e implementadas; gates A/B/C pendientes.

## Decisiones que concretar en H0

| Decisión | Propuesta inicial | Condición para avanzar |
| --- | --- | --- |
| Puerto de contextualización | ResponseContextPort de Conversation/Application y contrato público neutral; entrega separada | Aprobar schemas, ownership, errores y tests de sustitución antes de adapter Telegram. |
| Routing | DecisionModelPort especializado; comandos de capability explícita pueden resolver sin modelo | Elegir adapter por benchmark y fijar thresholds sobre desarrollo; fake solo acredita contratos. |
| Perfiles | General, Ventas, Marketing con capabilities de asesoría y configuración versionada | Validar IDs de capability y reglas de datos faltantes; no habilitar tools por describirlas en el perfil. |
| Contexto | Pares completos + hechos tipados, sin resúmenes automáticos ni RAG | Fijar presupuesto por perfil y precedencia de fuentes; pruebas de aislamiento y overflow. |
| Presupuesto real | Conservar límites vigentes hasta configurar un presupuesto explícito de etapa 2 | Resolver el cupo 6/6 de octubre registrado en etapa 1 antes de evaluar proveedores; no resetearlo para eludirlo. |
| Identidad | Bindings administrados de bot/chat/remitente; chats privados autorizados | Rechazo de desconocidos y destinos fuera de scope probado antes de usar red. |
| Persistencia | SQLite local detrás de puertos, un runner por bot | Especificar transacciones, locking, retención y recuperación; durable requerido para Gate A de reinicios. |
| Entrega incierta | UNKNOWN_EFFECT sin retry automático | Clasificación de errores y procedimiento de revisión documentados antes de Gate B. |
| Concurrencia | Serialización por conversación; reservas atómicas | Elegir sync/async sin bloquear recepción durable; timeout y cancelación definidos por operación. |
| Rendimiento | Medir contra referencia de plataforma ≤5 s | Fijar umbral de piloto y tamaño de muestra antes de evaluación; reportar incumplimientos. |

Estas son decisiones locales propuestas para un corte de implementación; no requieren cerrar todos los ADR globales para avanzar con fakes. Sí requieren un registro concreto y pruebas antes de habilitar el efecto externo. Si una decisión contradice un ADR aceptado, se ajusta el diseño o se tramita su evolución; no se presenta la excepción como cumplimiento.

## Decisiones cerradas en la revisión de ingeniería (2026-10-06)

| ID | Decisión | Dónde se concreta |
| --- | --- | --- |
| D1 | Presupuesto `eval-e2` separado (150 llamadas, 400 tokens, tope USD a registrar) | GOALS § Definición de terminado |
| D2 | Runner síncrono de un solo proceso e hilo; sin asyncio; puertos siguen síncronos | TELEGRAM § Runner |
| D3 | Decision Model = OpenAI con salida JSON schema; benchmark = keywords vs. adapter sobre `routing-v2` `val` | IMPLEMENTACION E2-05 |
| D4 | Terminología normativa | GLOSARIO |

Con D2, las filas «Concurrencia» y «sync/async» de la tabla anterior quedan resueltas. «Doble worker» se prueba como dos conexiones SQLite compitiendo por la misma reserva, no como dos runners.

## Riesgos y mitigaciones verificables

| Riesgo | Mitigación y evidencia |
| --- | --- |
| Llamar especialización a cambiar el saludo | Rúbrica de calidad, ejemplos con contexto/faltantes y salida útil por perfil. |
| Usar specialty como capability o modelo | Tipos separados; router no devuelve agentes/modelos; registry exacto y pruebas con dos versiones. |
| Historial ampliado mezcla chats o consume presupuesto | Scope en repositorios/queries, canarios y tests de ventana/tokens. |
| Compartir prompt interno con Telegram | Contexto de inferencia separado de respuesta pública y mapper con campos permitidos. |
| Creer que UUID implica idempotencia | Reserva durable por evento externo y reutilización de IDs/resultados; tests concurrentes y tras reinicio. |
| Repetir mensajes tras timeout | Ledger de entrega, SENDING → UNKNOWN_EFFECT y cero retry ciego. |
| Confundir respuesta de canal con tool arbitraria | Delivery desde Application, destino vinculado y policy; envío proactivo futuro pasa por ADR-005/021. |
| Prometer cumplimiento de plataforma | Goals locales explícitos; tools/RAG/model routing/tenancy productiva siguen pendientes. |

## Revisión previa a cada gate

- [ ] H0: decisiones locales y configuración registradas; schemas y criterios de evaluación congelados.
- [ ] Gate A: suite sin red completa y fallos de inbox/outbox reproducibles; ninguna dependencia del canal en core.
- [ ] Gate B: piloto autorizado y acotado con transporte real, scopes aislados y procedimiento de recuperación.
- [ ] Gate C: evaluaciones reales, costo/latencia y limitaciones con evidencia; pendientes no marcados como terminados.
