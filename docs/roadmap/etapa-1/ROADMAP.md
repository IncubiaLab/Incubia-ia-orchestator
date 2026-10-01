# Roadmap — primera etapa del MVP

## Resultado buscado

Un chatbot local ejecutado desde la terminal que recibe texto, elige una de hasta tres especialidades y responde mediante un workflow de LangGraph. La etapa termina cuando se puede iniciar una sesión, intercambiar varios turnos y observar qué especialidad respondió, con pruebas reproducibles y sin servicios de datos.

Esta etapa acota el MVP amplio descrito en [las specs](../../specs/README.md). La entrada HTTP de la spec 05 se difiere; el contrato de ejecución del ADR-ORCH-007 y el aislamiento de LangGraph del ADR-ORCH-001 siguen vigentes. No se implementan tools, RAG, base de datos, autenticación, persistencia, handoff ni canales externos.

## Stack inicial propuesto

| Pieza | Elección para esta etapa | Motivo |
| --- | --- | --- |
| Lenguaje y empaquetado | Python 3.12, `pyproject.toml` | Un solo entorno y dependencias declaradas. |
| CLI | `argparse` de la biblioteca estándar | Comandos pequeños sin framework adicional. |
| Orquestación | LangGraph | ADR-ORCH-001 aceptado. |
| Modelos | `LLMPort` y adapter OpenAI configurable | Permite sustituir proveedor; ADR-ORCH-013 sigue propuesto. |
| Pruebas | `pytest` y fake LLM | Verificación local sin red ni credenciales. |

Las versiones de paquetes y los identificadores de modelos se fijan y bloquean al iniciar la implementación, después de una prueba de compatibilidad. El programa se distribuye como comando de consola `incubia`.

## Hitos y entregables

| Hito | Entregable | Criterio de salida |
| --- | --- | --- |
| 0. Decisiones | ADRs incorporados y stack inicial documentado | Se distingue qué decisiones están aceptadas, propuestas y abiertas; el alcance CLI queda explícito. |
| 1. Contratos y composición | Paquete Python, tipos de ejecución del ADR-ORCH-007, `WorkflowRuntimePort`, `LLMPort`, configuración y bootstrap | Application no importa LangGraph ni SDK del proveedor; arranque sin secretos en el repositorio. |
| 2. Conversación en terminal | Comando `incubia chat`, lectura de texto, salida, `/help`, `/exit`, errores seguros e historial de sesión en memoria | Varios turnos funcionan en un proceso; reiniciar descarta la sesión. |
| 3. Orquestación especialista | Grafo LangGraph con selección y hasta tres perfiles; una sola invocación especialista por turno | Casos representativos se enrutan al perfil correcto; casos ambiguos usan una regla explícita. |
| 4. Verificación de etapa | Tests de contratos, routing, graph y CLI con LLM falso; prueba manual optativa con proveedor configurado | La suite local pasa sin red; la salida identifica la especialidad y no revela secretos ni estado interno de LangGraph. |

## Secuencia de implementación

1. Definir el contrato de generación, los IDs y los errores; implementar un adapter LLM falso.
2. Componer el grafo: entrada → selección de especialidad → generación → salida. El routing inicial será determinista y verificable. Registrar la decisión de routing antes de adoptar un clasificador LLM.
3. Crear el adapter del proveedor y configurar por entorno los modelos permitidos, límites de salida y timeout.
4. Exponer el caso de uso en la CLI, manteniendo el historial únicamente en memoria durante el proceso.
5. Probar solicitudes de cada especialidad, ambigüedad, entrada vacía, fallo del proveedor, salida y continuidad de varios turnos.

## Criterios de aceptación de la etapa

- Desde una terminal se puede iniciar el chat y mantener una conversación de varios turnos.
- Hay entre uno y tres perfiles activos; cada perfil tiene propósito, instrucciones y modelo configurado. No se invocan más de tres configuraciones de modelo distintas.
- Cada turno produce una respuesta o un error legible, con especialidad seleccionada y `request_id` para diagnóstico.
- No hay ejecución de herramientas, acceso a archivos del usuario, consultas a bases de datos ni llamadas a sistemas externos excepto al proveedor LLM configurado.
- El historial existe solo durante el proceso y tiene un límite configurable de turnos o tokens para controlar costo y contexto.
- Tests locales con fake LLM cubren routing, contrato, errores y conversación; no necesitan credenciales ni red.

## Decisiones pendientes antes de construir

| Decisión | Propuesta para esta etapa |
| --- | --- |
| Especialidades | General, arquitectura y programación; son perfiles de trabajo iniciales, ajustables tras probar solicitudes reales. |
| Routing | Reglas deterministas con fallback a General; documentar y probar ejemplos. El ADR-ORCH-003 permanece pendiente. |
| Proveedor y modelos | Adapter OpenAI previsto por ADR-ORCH-013, aún propuesto. Elegir IDs concretos por configuración y medir costo, calidad y latencia antes de fijarlos. |
| Formato de mensajes | Texto plano; salida opcional de metadatos mínimos. |
| Gestión de contexto | Historial efímero limitado; no hay memoria persistente ni checkpoints durables. |

## Después de esta etapa

La API HTTP, identidad y tenant, persistencia, RAG, herramientas, auditoría, observabilidad de producción y handoff se priorizan en un roadmap posterior con sus ADR y requisitos propios. Los objetivos de carga y aislamiento multi-tenant de [spec 06](../../specs/06-pruebas-y-nfr.md) no son criterios de cierre de este prototipo local.
