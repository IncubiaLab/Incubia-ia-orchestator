# Revisión y complemento del ROADMAP de la etapa 1

Fecha: 2026-10-01 · Estado: **propuesta revisada; implementación y validación pendientes**.

Este documento complementa [ROADMAP.md](ROADMAP.md) con brechas, decisiones y evidencias de aceptación de [GOALS.md](GOALS.md). La base se especifica en [BASE.md](BASE.md). La etapa usa únicamente terminal; HTTP queda diferido.

Esta revisión sustituye el plan operativo anterior. Sus tablas de consenso y puntuaciones no constituían evidencia de implementación. El estado actual comprobado es un graph.py experimental con tres ramas de respuesta fija y requirements.txt; todavía no existen pyproject.toml, contratos ni adapters implementados. Las rutas de código siguientes son propuestas.

## 1. Evaluación del complemento anterior

**Cumplía parcialmente su cometido.** Identificaba brechas reales en evaluación, latencia/costo, errores, logs y reproducibilidad. Mezclaba requisitos de cierre de etapa con los de la base y presentaba algunas decisiones abiertas como resueltas.

| Hallazgo | Consecuencia | Corrección |
| --- | --- | --- |
| No había cierre verificable del flujo sin router. | Un grafo aislado podía interpretarse como base completa. | Gate 0 técnico en BASE: contratos → puerto → adapter → grafo mínimo → FakeLLM → outcome. |
| Hito 1 acumulaba historial, especialidad, perfiles y proveedor real. | La base dependía de hitos posteriores. | Base de un mensaje; conversación y routing después. |
| La adenda a ADR-007 aparecía como única solución al historial. | Se imponía una forma de contrato todavía abierta. | Decidir contexto antes del hito 2 y selección antes del 3; registrar evolución del contrato aceptado. |
| Se mezclaba resume no soportado con cobertura de suspended en el runtime. | Podía declararse cumplimiento de una capacidad ausente. | Distinguir serialización de variantes, soporte inicial y suspensión/reanudación funcional pendiente. |
| Se exigía ratificar o exceptuar todos los ADR propuestos antes de empezar. | Bloqueo global innecesario para preparar la base. | Registrar adopción provisional y desviaciones concretas; conservar estados de Linear. |
| Se prometían timeout total y cancelación de llamada síncrona sin mecanismo. | El plan no justificaba cómo interrumpir trabajo bloqueante. | Elegir y probar mecanismo al integrar proveedor; timeout del SDK no acredita por sí solo deadline total. |
| El canario de contenido debía faltar en toda salida. | Contradecía mostrar la respuesta en stdout. | Proteger logs/diagnósticos; en stdout comprobar secretos y contenido interno ajeno a la respuesta prevista. |
| Plan de pruebas enlazado a archivo personal externo. | Otro desarrollador no podía reproducir el cierre. | Criterios en BASE y este documento; fixtures/scripts versionados al implementar. |

## 2. Precedencia y función de cada documento

- ADR-001/006/007 aceptados fijan fronteras y lifecycle. Nombres vigentes: StartExecutionRequest, ResumeExecutionRequest, ExecutionOutcome, start y resume. ADR-006 requiere invariantes de kernel, Policy Engine con PDP/PEP y guardrails separados; la inferencia pasa por enforcement cercano y falla cerrada si no puede evaluarse.
- ROADMAP fija alcance y orden; BASE detalla cierre de hitos 0–1; este complemento detalla comprobaciones restantes.
- GOALS define el cierre completo. Cerrar la base todavía no satisface conversación, routing ni mediciones reales.
- ADR 013/017/018/019/020 continúan Proposed. Las elecciones locales no cambian su estado en Linear.
- Las specs describen el MVP amplio. En esta etapa la CLI sustituye el HTTP de specs 03/05 y conserva sus restricciones arquitectónicas.

## 3. Secuencia y puertas de avance

| Hito | Trabajo y evidencia | Dependencia |
| --- | --- | --- |
| 0. Decisiones | Tipos mínimos, scope local, Policy PEP/PDP, firmas y límites de lifecycle; separar ADR aceptado y propuesta local. | ADR-001/006/007 y BASE. |
| 1. Base | Mensaje por caso de uso, PolicyEnginePort, adapter in-process, PEP antes de LLM, puertos, LangGraph, mapper y FakeLLM; enforcement, integración y arquitectura probados. | Hito 0. Sus evidencias cierran el Gate 0 técnico para la ruta permitida; no acreditan REQUIRE_APPROVAL/resume funcional. |
| 2. Conversación | REPL de ≥3 turnos, historial limitado, ayuda/salida, diagnósticos y proveedor real configurable. | Base comprobada y decisión de contexto. |
| 3. Especialistas | Router puro inyectado, generación parametrizada, 1–3 perfiles, especialidad visible y eval versionado. | Hito 2 y representación de especialidad. |
| 4. Cierre | Suite sin red, guía y medición manual real de latencia/costo. | GOALS completo; si falta medición real queda pendiente. |

Para el hito 3 se propone `START → select_specialty → generate_response → END`. La política pertenece a Application y el nodo la ejecuta. Un solo nodo genera mediante LLMPort con el perfil seleccionado.

## 4. Decisiones al entrar en cada hito

| Decisión | Propuesta | Momento / criterio |
| --- | --- | --- |
| Contexto | Historial en Application; misma ventana acotada para los perfiles. | Antes del hito 2: transporte tipado, responsable y serialización. Si cambia ADR-007, documentar evolución. |
| Ventana | Diez pares usuario/asistente por defecto y límite por mensaje; descartar pares antiguos completos; fallo no añade medio turno. | Hito 2; probar 0, N y N+1 y documentar unidades/límites. |
| Especialidad | Campo propio tipado visible en CLI; definir ausencia en fallo previo al routing. | Antes del hito 3; sin metadata libre ni nombres de nodos como contrato. |
| Routing | Reglas deterministas, fallback General y motivo sin contenido del usuario. | Hito 3; ADR-003 pendiente; casos ambiguos y desempates explícitos. |
| Proveedor | OpenAI configurable y fake explícito para demo. | Hito 2; verificar modelos/parámetros y versiones al implementar. Sin clave: error seguro sugiriendo --fake. |
| Sync/async y cancelación | Flujo síncrono propuesto para base; revisar según límites del proveedor real. | Antes del adapter real: intentos, presupuesto y Ctrl-C. Dejar de esperar un trabajo bloqueante no implica cancelarlo. |
| Baseline General | Comparación opcional usando el mismo runtime y proveedor, con routing desactivado. | Hito 4; requiere rúbrica de calidad. Precisión de routing no prueba valor de especialistas. |

Son decisiones técnicas y de producto pendientes donde se indica; no preferencias de estilo ni acuerdos ratificados por consenso automático.

## 5. Errores, timeout y diagnósticos

La base convierte fallos a errores propios. En el hito 2 se amplía la taxonomía:

| Categoría | Ejemplo | Comportamiento |
| --- | --- | --- |
| Entrada | Vacía, larga, comando desconocido. | Rechazo previo a generación; historial intacto. |
| Configuración | Clave ausente, perfil/modelo inválido. | Validar lo detectable al arrancar. Autenticación rechazada remotamente también puede descubrirse durante un turno y debe mapearse entonces a fallo seguro. |
| Proveedor | Timeout, límite de peticiones, fallo remoto, respuesta vacía/incompleta. | Error propio del adapter y FailedExecution; sesión usable. Detalles según API elegido. |
| Routing | Ambigüedad o falta de coincidencia. | Fallback esperado a General; contabilizar separado del fallo técnico del router. |
| Runtime | Fallo técnico del grafo. | Error seguro del producto con IDs de correlación. |

Configurar explícitamente timeout e intentos. Valor propuesto por llamada: 30 s; no fijar retries antes del presupuesto total. Con transporte simulado, verificar qué se limita: llamada, intento o turno completo. Un deadline total requiere mecanismo efectivo y prueba específica.

Logs: request_id, estado, categoría y latencia; después del routing, perfil y código de motivo. Sin prompts, historial, respuestas ni excepciones crudas por defecto. Probar secretos canario en todas las salidas y contenido canario en logs/diagnósticos. La respuesta prevista del asistente sí pertenece a stdout.

## 6. CLI y experiencia

| Elemento | Alcance |
| --- | --- |
| Base | `incubia chat --fake -m "texto"`: un mensaje por el recorrido completo. |
| Hito 2 | `incubia chat`, /help, /exit, EOF, errores seguros; fake sin clave. |
| Salidas | Respuesta en stdout; errores y pie request_id/latencia en stderr. Especialidad desde hito 3. |
| Códigos propuestos | 0 éxito/salida normal, 2 uso/configuración, 3 fallo de ejecución de un turno, 130 interrupción. |
| No interactivo | Leer hasta EOF sin banner ni prompt. |
| Ctrl-C | En prompt: salida limpia. Durante generación: cancelación comprobable o salida segura según mecanismo elegido; sin turno parcial. |
| Extras diferibles | /reset, --profile, --no-meta, --debug y colores no condicionan el Gate 0. |

La guía documentará proveedor, clave, modelos, límites, timeout, intentos, historial y logging con nombres/defaults definitivos. No fijar parámetros del SDK sin validar compatibilidad. .env.example usa marcadores y los secretos quedan fuera del repositorio.

## 7. Trazabilidad GOALS → evidencia

| Objetivo | Evidencia requerida | Hito |
| --- | --- | --- |
| 1. Experiencia | ≥3 turnos; tercero recibe historial esperado; ayuda, salida y EOF. | 2 y 4 |
| 2. Orquestación | Casos por perfil y ambiguos; una generación por turno; especialidad visible. | 3 |
| 3. Alcance | Validar 1–3 perfiles, General para fallback y ≤3 configuraciones de modelo; sin tools/BD/canales. | 3 |
| 4. Arquitectura | Evidencias de BASE; ampliar tests de contratos/fronteras al añadir contexto, proveedor y routing. | 1–4 |
| 5. Confiabilidad | Fallos seguros, IDs, latencia, límites comprobados y canarios. | 1, 2 y 4 |
| 6. Reproducibilidad | Runtime real con LLM falso, sin credenciales; bloqueo de red verificado también en subprocesos si se usan. | 1–4 |
| Routing ≥80 % | Dataset versionado, etiquetas, partición de validación fijada antes de afinar reglas; reporte aciertos/total con ambiguos. | 3 y 4 |
| Latencia/costo | Modelos reales: configuración, fecha, muestras, latencia, tokens y fuente/fecha de precios. Uso desconocido es no disponible, no cero. | 4 |
| Fallos por tipo | Registro y conteo por categoría; separar fallback esperado de error técnico. | 2–4 |
| Guía de arranque | Instalación, demo, configuración real, sesión, pruebas y limitaciones. | 1 y 4 |
| Estado ADR | Mantener [índice](../../adr/README.md) y decisiones locales sin promover propuestas a Accepted. | 0–4 |

La medición manual real es requerida por GOALS para terminar la etapa; no condiciona los tests locales ni el Gate 0. Fake valida recorrido e instrumentación, pero no costo o calidad del modelo real.

## 8. Backlog ordenado

- [ ] Hito 0: registrar decisiones mínimas de BASE y recorte explícito de lifecycle.
- [ ] Hito 1: completar evidencias del Gate 0 técnico en BASE.
- [ ] Hito 2: resolver contexto; implementar conversación, adapter real y fallos/timeout verificables.
- [ ] Hito 3: resolver especialidad tipada; añadir router, perfiles, configuración y dataset.
- [ ] Hito 4: ejecutar suite, medir con proveedor real y completar guía; declarar cualquier evidencia pendiente.

No hay pruebas de ejecución ni gates cerrados como resultado de esta revisión documental.
