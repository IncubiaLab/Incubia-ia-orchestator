# Perfiles especialistas del chatbot

Un especialista es un perfil de instrucciones; los tres comparten el modelo configurado. El valor inicial para pruebas con API es `gpt-4o-mini`, reemplazable con `--model` o `INCUBIA_MODEL`. El modo `--fake` no llama al modelo ni requiere credenciales.

| Perfil | Propósito | Selección inicial |
| --- | --- | --- |
| General | Saludos, consultas generales y solicitudes ambiguas | Fallback o coincidencia con más de un área. |
| Ventas | Clientes, prospectos, cotizaciones, negociación y cierre | Términos de ventas sin coincidencia de marketing. |
| Marketing | Campañas, publicidad, audiencias, marca y SEO | Términos de marketing sin coincidencia de ventas. |

El router es determinista y puro. Evalúa el mensaje actual, no el historial; usa palabras completas sin distinguir mayúsculas ni tildes. Si encuentra señales de ventas y marketing, elige General. La selección es visible en el outcome y la CLI. El conjunto inicial de ejemplos está en `evals/routing-v1.jsonl`; ampliar ese conjunto antes de afinar reglas con solicitudes reales.

Cada perfil tiene instrucciones distintas y pide comenzar con un saludo identificable. El fake devuelve de forma determinista `Hola, el enrutador me escogió y soy el especialista en <perfil>` para comprobar el flujo. El texto generado por el proveedor real puede variar; la especialidad estructurada del outcome es la fuente fiable para verificar el routing.

No hay tools, acceso a datos empresariales, agentes autónomos ni permisos adicionales por perfil. La policy de inferencia se aplica después de seleccionar y antes de llamar al LLM.
