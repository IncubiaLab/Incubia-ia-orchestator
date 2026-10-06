# Especialistas — características, capacidades y contexto

Estado: diseño propuesto. Los perfiles actuales siguen siendo los de etapa 1 hasta implementar H1/H2.

## Modelo compartido

Separar `SpecialtyProfile` (comportamiento y contexto) de `AgentDescriptor` (descubrimiento del ADR-004). El perfil propone: profile_id/version, specialty, propósito, instrucciones, estilo, capacidades, exclusiones, campos requeridos/opcionales, ejemplos, output_contract y límites de contexto/salida. El descriptor declara agent_id/version, capabilities, requisitos técnicos, modalidades, execution_mode, scope, policy_tags y estado. Ninguno contiene credenciales ni autoridad concedida por el propio agente.

Bootstrap registra descriptores y factories de forma explícita. Discovery usa capability matching estructurado y devuelve candidatos; Selection aplica prioridad configurada y desempate estable. Puede haber dos versiones candidatas sin modificar el router. Conservar la versión elegida en la ejecución. `Specialty` sigue como etiqueta pública compatible con CLI, no como clave que sustituya capability/agent identity.

## Caracterización inicial

| Perfil | Capability inicial propuesta | Comportamiento y salida útil | Contexto necesario | Límites |
| --- | --- | --- | --- | --- |
| General | `conversation.assistance` | Explicar alcance, responder consultas generales dentro del contexto o formular una pregunta concreta de aclaración. Tono claro; no repetir saludo en cada turno. | Idioma, objetivo actual, hechos compartidos pertinentes y últimos turnos. | No elegir una capability empresarial por mera confianza ni prometer acciones; ambigüedad se conserva como tal. |
| Ventas | `sales.advice` | Diagnóstico breve de oportunidad, recomendación y siguiente paso; producir borrador de propuesta cuando hay datos suficientes. Tono consultivo, sin presión artificial. | Producto/oferta aprobada, necesidad declarada, etapa comercial, objeciones, restricciones y precios solo si fueron suministrados con fuente. | No inventar clientes, descuentos, stock o precios; no crear leads ni cotizaciones oficiales; pedir el dato que impide avanzar. |
| Marketing | `marketing.planning` | Proponer objetivo, audiencia, mensaje, canal e indicador a medir; distinguir hipótesis de evidencia. Tono creativo y concreto. | Brief, audiencia, tono de marca, objetivo, canales permitidos, presupuesto si se conoce y métricas con fuente/fecha. | No inventar ROI, métricas ni resultados; no publicar campañas ni acceder a cuentas publicitarias. |

Los IDs de capability se validan en H0; describen asesoría sin herramientas empresariales. Una solicitud de precio en tiempo real, CRM, publicación o envío a terceros es UNSUPPORTED, aunque contenga vocabulario de ventas/marketing. General puede redactar la aclaración segura, pero no convertir un estado AMBIGUOUS/UNSUPPORTED en RESOLVED artificialmente.

## Paquetes y selección de contexto

Cada `SpecialtyContext` contiene hechos tipados con origen, versión/fecha y scope; campos requeridos ausentes; pares recientes pertinentes; objetivo del turno y presupuesto. Fuentes iniciales: configuración aprobada versionada por deployment/tenant y hechos aportados por la conversación. No se incluye RAG ni lectura arbitraria de archivos por el agente.

Orden de construcción: invariantes e instrucciones de perfil → hechos aprobados pertinentes → objetivo y datos explícitos del usuario → pares recientes completos → mensaje actual. La prioridad de autoridad no depende del orden textual: datos del usuario o historia nunca reemplazan instrucciones ni policy. Marcar hechos del usuario como declarados, no verificados.

Presupuesto propuesto: `max_input_tokens`, `max_output_tokens`, `max_history_pairs` y `max_context_items` por perfil, acotados por deployment. H0 fija valores y estrategia de conteo compatibles con el modelo y presupuesto real. Descartar primero contexto opcional antiguo; preservar mensaje actual y restricciones. Si lo obligatorio no cabe, producir error tipado o pedir reducción; no cortar silenciosamente instrucciones. No introducir resúmenes generados automáticamente en este corte.

Al cambiar Ventas → Marketing conservar solo hechos compartidos pertinentes (producto/objetivo/idioma), seleccionar el brief de Marketing y excluir instrucciones internas del perfil anterior. Al volver a Ventas recuperar hechos comerciales autorizados de la conversación canónica, no GraphState. Cada chat mantiene estado separado aunque use el mismo actor; unir identidades entre Telegram y WhatsApp queda fuera de alcance.

## Escenarios de aceptación

| Perfil | Caso | Resultado esperado |
| --- | --- | --- |
| General | «Hola, ¿qué puedes hacer?» | Explicar capacidades actuales y pedir objetivo. |
| General | «Quiero vender y hacer publicidad, ¿por dónde empiezo?» | AMBIGUOUS cuando falta prioridad; una pregunta discriminante. |
| Ventas | Producto y objeción disponibles; «¿cómo respondo?» | Recomendación basada en esos hechos y siguiente paso. |
| Ventas | «Dame el precio actual» sin catálogo válido | No inventar; explicar falta de fuente/acceso. |
| Marketing | Brief con audiencia/objetivo; «propón una campaña» | Plan breve con hipótesis, canal y medición; ningún envío real. |
| Marketing | «¿Qué ROI tuvimos?» sin resultados | Pedir datos; no fabricar cifras. |
| Transversal | Cambio de perfil, dato faltante y petición de ignorar policy | Continuidad pertinente, aclaración y respeto a límites. |
| Transversal | Historia de otro tenant/chat o instrucciones embebidas en un brief | Aislamiento y tratamiento como datos sin elevar autoridad. |

La evaluación de GOALS añade paráfrasis y escenarios nuevos a estos ejemplos; no ajusta el modelo únicamente a estas frases. Mayor contexto significa mejor selección de información y respuestas útiles, no prompts ilimitados ni permisos adicionales.
