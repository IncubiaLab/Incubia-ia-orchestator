# Roadmap — etapa 2: especialistas y primer canal E2E

Fecha: 2026-10-06 · Estado: planificación propuesta; implementación pendiente.

## Resultado buscado

Evolucionar el chatbot local hacia tres especialistas con capacidades, instrucciones, contexto y criterios de calidad propios. Completar un primer recorrido E2E por Telegram mediante un adaptador reemplazable, conservando un puerto de contextualización común para Telegram, WhatsApp y futuros canales. «Tier 2» se usa aquí como segunda etapa de desarrollo; no designa un nivel de modelos ni el hito 13 completo de Linear.

La [etapa 1](../etapa-1/VERIFICACION.md) está cerrada para su alcance local. Esta fase sigue los ADR-ORCH-001/003/004/005/006/007 aceptados y mantiene explícitas las decisiones abiertas. La [revisión de Linear](LINEAR-ADR.md) es el corte de evidencia del 6 de octubre; no se modificaron issues ni estados externos.

## Documentos de trabajo

| Documento | Uso |
| --- | --- |
| [GOALS](GOALS.md) | Objetivos medibles y definición de terminado. |
| [BASE](BASE.md) | Fronteras, puertos y contratos propuestos. |
| [AGENTES](AGENTES.md) | Caracterización de General, Ventas y Marketing; contexto y evaluación. |
| [TELEGRAM](TELEGRAM.md) | Primer adaptador, identidad, idempotencia y fallos de entrega. |
| [IMPLEMENTACION](IMPLEMENTACION.md) | Backlog secuenciado con dependencias y rutas objetivo. |
| [AUTOPLAN-REVIEW](AUTOPLAN-REVIEW.md) | Decisiones abiertas, riesgos y condiciones de avance. |
| [VERIFICACION](VERIFICACION.md) | Plan de pruebas y evidencias pendientes. |
| [LINEAR-ADR](LINEAR-ADR.md) | Fuentes, estados y correspondencia con goals de plataforma. |

## Alcance

Un proceso de monolito modular, tres perfiles versionados, una capacidad principal por turno, discovery in-process y contexto seleccionado con presupuesto explícito. El routing semántico pasa por `DecisionModelPort`; seleccionar al especialista ocurre después de resolver la capability. CLI continúa como entrada de regresión. Telegram inicia con long polling, texto y chats privados de prueba autorizados.

Se propone almacenamiento local durable detrás de puertos para conversación, inbox y entregas: SQLite como primera opción a validar en H0. Esto amplía deliberadamente el recorte «sin BD» de etapa 1 para poder comprobar reinicios e idempotencia. No implica adoptar persistencia de producción ni checkpoints como conversación canónica.

## Hitos y gates

| Hito | Entregable | Criterio de salida |
| --- | --- | --- |
| H0. Contratos y decisiones | Modelos de contexto, canal e identidad; estrategia de persistencia/retry; presupuesto y candidato de Decision Model | Decisiones de AUTOPLAN registradas; schemas y límites versionados; ningún ADR abierto promovido tácitamente. |
| H1. Especialistas y contexto | Perfiles de AGENTES, paquetes de contexto y selección acotada | Casos por perfil pasan con fake; rechazo de contexto ajeno; CLI compatible. |
| H2. Routing y discovery | DecisionModelPort, RouteDecision, AgentDiscoveryPort y registro en bootstrap | Eval de routing y scope aprobado; selección sin agentes hardcodeados en router; prueba de sustitución de adapters. |
| H3. Frontera multicanal | Puerto de contextualización, inbox/outbox durable y adaptador de canal fake | **Gate A:** recorrido completo sin red; duplicados, concurrencia, reinicios y estado incierto probados. |
| H4. Telegram piloto | Adapter de entrada/salida y runner por long polling | **Gate B:** tres turnos desde Telegram, aislamiento entre dos chats autorizados, fallos y replay controlados; primero con LLM fake. |
| H5. Evaluación y cierre | Calidad con proveedor real, informe E2E y operación reproducible | **Gate C:** GOALS completo, evidencias con fecha/configuración y restricciones explícitas. |

Secuencia: H0 → H1 → H2 → H3 → H4 → H5. El diseño del canal puede precisarse mientras se caracterizan perfiles, pero no se activa entrega real antes del Gate A. El primer incremento implementable es E2-01/E2-02 en IMPLEMENTACION, no la conexión del bot.

## Fuera de alcance

WhatsApp real, grupos, audio, adjuntos, UI web, campañas o mensajes proactivos, CRM/leads persistidos en sistemas externos, RAG/vector store, tools empresariales, handoff entre agentes, aprobaciones/resume funcionales, entrenamiento/fine-tuning y selección multi-modelo de producción. El envío de la respuesta por el canal es el único efecto externo nuevo. La integración de una segunda plataforma se demuestra con un adapter fake y los mismos contratos.

## Condición de cierre

Los gates se cierran con resultados, no con estos documentos. Si solo pasa Telegram + FakeLLM, se acredita el transporte, no la calidad de especialistas con modelo real. No se declara completado HEC-12, HEC-11 ni HEC-17 por terminar este corte. Las fechas del proyecto Linear no se convierten automáticamente en compromisos de esta etapa.
