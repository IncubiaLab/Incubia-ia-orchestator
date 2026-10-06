# Roadmap — primera etapa del MVP

## Resultado buscado

Un chatbot local ejecutado desde la terminal que recibe texto, elige una de hasta tres especialidades y responde mediante un workflow de LangGraph. La etapa termina cuando se puede iniciar una sesión, intercambiar varios turnos y observar qué especialidad respondió, con pruebas reproducibles y sin servicios de datos.

Esta etapa acota el MVP amplio descrito en [las specs](../../specs/README.md). La entrada HTTP de la spec 05 se difiere; el contrato de ejecución del ADR-ORCH-007 y el aislamiento de LangGraph del ADR-ORCH-001 siguen vigentes. No se implementan tools, RAG, base de datos, autenticación, persistencia, handoff ni canales externos.

## Cómo construir la base

El primer entregable es un mensaje de extremo a extremo por `HandleMessage → WorkflowRuntimePort.start → LangGraphRuntimeAdapter → LLMPort → FakeLLM`, con retorno como `ExecutionOutcome`. El grafo inicial es `START → generate_response → END`.

[BASE.md](BASE.md) define responsabilidades, contratos y pruebas para cerrar el **Gate 0 técnico**, que abarca los hitos 0 y 1 de este roadmap. El grafo aislado con tres perfiles no acredita ese gate. La conversación y la selección de especialistas se incorporan después de verificar las fronteras.

[AUTOPLAN-REVIEW.md](AUTOPLAN-REVIEW.md) complementa este orden con decisiones pendientes, errores, evaluación y trazabilidad hacia [GOALS.md](GOALS.md). Todos son documentos de planificación; los gates se cierran con evidencia de implementación. Los ADR propuestos conservan su estado aunque se adopten provisionalmente sus diseños.

## Stack inicial propuesto

| Pieza | Elección para esta etapa | Motivo |
| --- | --- | --- |
| Lenguaje y empaquetado | Python 3.12, `pyproject.toml` | Un solo entorno y dependencias declaradas. |
| CLI | `argparse` de la biblioteca estándar | Comandos pequeños sin framework adicional. |
| Orquestación | LangGraph | ADR-ORCH-001 aceptado. |
| Modelos | `LLMPort` y adapter OpenAI configurable | Permite sustituir proveedor; ADR-ORCH-013 sigue propuesto. |
| Pruebas | `pytest` y fake LLM | Verificación local sin red ni credenciales. |

Las versiones de paquetes están fijadas en `requirements.lock`. El modelo compartido actual es `gpt-4o-mini`, configurable; la validación real mínima está en VERIFICACION.md. El programa se distribuye como comando de consola `incubia`.

## Hitos y entregables

| Hito | Entregable | Criterio de salida |
| --- | --- | --- |
| 0. Decisiones | ADRs incorporados, stack y decisiones mínimas de BASE documentados | Estados aceptado/propuesto explícitos; scope local, Policy PEP/PDP y recorte de lifecycle registrados. Historial/especialidad se deciden en sus hitos. |
| 1. Contratos y composición | Paquete, contratos ADR-007, PolicyEnginePort y adapter in-process, PEP antes de inferencia, LLMPort, mappers, grafo mínimo, FakeLLM y bootstrap | Evidencias de BASE completas: enforcement probado para ALLOW/DENY/INDETERMINATE, recorrido por puertos, outcomes seguros, serialización y fronteras. Cierra Gate 0 técnico. REQUIRE_APPROVAL y resume funcional quedan explícitamente fuera del alcance acreditado. |
| 2. Conversación en terminal | Contrato de contexto resuelto; `incubia chat`, `/help`, `/exit`, historial en memoria, logs mínimos y adapter real configurable | Al menos tres turnos con fake; límites de historial y fallos del proveedor probados; reiniciar descarta sesión. |
| 3. Orquestación especialista | Selección tipada, router puro y nodo de generación parametrizado; 1–3 perfiles y eval versionado | Una generación por turno, especialidad visible y ≥80 % de aciertos en validación, con ambiguos y fallback explícitos. |
| 4. Verificación de etapa | Suite sin red, guía de arranque e informe manual de latencia/costo con proveedor real | GOALS completo; logs/diagnósticos sin contenido ni secretos; si falta medición real, el cierre queda pendiente. |

## Secuencia de implementación

1. Construir y comprobar la base de un mensaje según BASE: contratos → puertos → caso de uso → FakeLLM → adapter LangGraph → bootstrap → entrada mínima. Cerrar el Gate 0 técnico.
2. Resolver el transporte tipado del contexto conversacional y documentar cualquier evolución del ADR-007; añadir REPL e historial acotado en Application.
3. Crear el adapter real y configurar modelos, límites, timeout e intentos; probar errores con transporte simulado antes de usar credenciales reales.
4. Resolver especialidad tipada y routing determinista; añadir selección antes de generación y evaluar con ejemplos versionados. ADR-003 permanece pendiente.
5. Verificar GOALS, registrar mediciones reales y completar la guía de arranque. Las llamadas reales se mantienen fuera de la suite local.

## Criterios de aceptación de la etapa

- Desde una terminal se puede iniciar el chat y mantener una conversación de al menos tres turnos.
- Hay entre uno y tres perfiles activos; cada perfil tiene propósito, instrucciones y modelo configurado. No se invocan más de tres configuraciones de modelo distintas.
- Cada turno produce una respuesta o un error legible, con `request_id` para diagnóstico y especialidad cuando se haya seleccionado; un fallo anterior al routing no inventa un perfil.
- No hay ejecución de herramientas, acceso a archivos del usuario, consultas a bases de datos ni llamadas a sistemas externos excepto al proveedor LLM configurado.
- El historial existe solo durante el proceso y tiene un límite configurable de turnos o tokens para controlar costo y contexto.
- Tests locales con fake LLM cubren routing, contrato, errores y conversación; no necesitan credenciales ni red.
- El dataset de routing está versionado y obtiene ≥80 % en su partición de validación; se registran fallos por categoría y latencia sin contenido ni secretos en logs.
- Existe guía de arranque e informe manual de latencia/costo con modelos reales. Las mediciones del fake no sustituyen esa evidencia.

## Decisiones pendientes por hito

| Decisión | Propuesta para esta etapa |
| --- | --- |
| Base (hito 0) | Tipos mínimos, firmas, scope local y limitación de resume descritos en BASE. No presentar el recorte como cumplimiento completo de suspensión/reanudación del ADR-007. |
| Contexto (antes del hito 2) | Historial en Application y transporte tipado hasta generación; registrar la evolución del contrato si corresponde. |
| Especialidad en el contrato (antes del hito 3) | Representación propia tipada de la selección y su ausencia antes de routing; sin metadata libre. |
| Especialidades | General, Ventas y Marketing, según la prueba mínima acordada; son perfiles iniciales ajustables. |
| Routing | Reglas deterministas con fallback a General; documentar y probar ejemplos. El ADR-ORCH-003 permanece pendiente. |
| Proveedor y modelos | Adapter OpenAI implementado provisionalmente; `gpt-4o-mini` compartido y reemplazable por configuración. Costo, calidad y latencia reales medidos en VERIFICACION.md. |
| Formato de mensajes | Texto plano; salida opcional de metadatos mínimos. |
| Gestión de contexto | Propuesta: ventana por pares completos en memoria, compartida entre perfiles; sin checkpoints durables. Concretar límites en hito 2. |

## Después de esta etapa

La API HTTP, identidad y tenant, persistencia, RAG, herramientas, auditoría, observabilidad de producción y handoff se priorizan en un roadmap posterior con sus ADR y requisitos propios. Los objetivos de carga y aislamiento multi-tenant de [spec 06](../../specs/06-pruebas-y-nfr.md) no son criterios de cierre de este prototipo local.

## Estado de verificación (2026-10-06)

Se completaron los pasos 1 a 5 dentro del alcance del prototipo local. El [informe](VERIFICACION.md) registra instalación limpia, suite sin red, tres turnos de prueba y una respuesta real por cada perfil, con latencia, tokens y costo estimado. Gate 0 técnico cerrado para la ruta local permitida; etapa 1 cerrada con las limitaciones indicadas en el informe.

Antes de añadir saldo de API, las llamadas con `gpt-4o-mini` y `gpt-5.4-mini` devolvieron `credit_balance_exhausted`. Tras añadir saldo, las tres pruebas reales terminaron con `gpt-4o-mini`. El cupo local conservador para llamadas reales quedó en 6/6 intentos en octubre de 2026.
