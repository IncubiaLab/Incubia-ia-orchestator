# Perfiles especialistas del chatbot

Este archivo describe los perfiles que el orquestador podrá seleccionar. Un perfil no es un proceso autónomo: es una configuración de instrucciones y modelo invocada para responder un turno. El máximo es **tres perfiles activos** y **tres configuraciones de modelo distintas**; se permite que varios perfiles compartan el mismo modelo.

| Perfil | Responsabilidad | Enviar aquí cuando | No asumir |
| --- | --- | --- | --- |
| General | Conversación, explicación y clasificación de solicitudes ambiguas | La solicitud no pertenece claramente a las otras dos áreas | Acceso a datos empresariales o memoria persistente |
| Arquitectura | Diseño de componentes, contratos, tradeoffs y roadmap técnico | Se pide diseñar o evaluar arquitectura | Que una propuesta de ADR está aceptada |
| Programación | Explicación de código, implementación sugerida y depuración conceptual | Se pregunta por código o errores de programación | Capacidad de ejecutar código o leer el repositorio mediante tools |

## Política de selección inicial

La selección ocurre antes de invocar el modelo especialista. Reglas simples y ejemplos versionados determinan el perfil; ante empate o baja confianza se usa General. Solo se invoca un perfil por turno. El selector no puede activar tools ni acceder a una base de datos. Se registra el perfil escogido para evaluación.

La conversación conserva los turnos en memoria del proceso con un límite configurable. La propuesta de etapa 1 es pasar la misma ventana acotada de pares usuario/asistente a todos los perfiles; no se presupone un selector de relevancia. El transporte tipado del historial se resuelve antes del hito 2, según [AUTOPLAN-REVIEW.md](AUTOPLAN-REVIEW.md). Las instrucciones de cada perfil no conceden permisos adicionales.

## Configuración pendiente

Las instrucciones finales, los identificadores de modelo, temperatura y límite de salida se fijarán en configuración y se evaluarán con solicitudes reales. Los nombres anteriores son una hipótesis inicial para esta primera etapa, no una taxonomía permanente del producto.
