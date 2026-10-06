# Telegram — primer adaptador E2E

Estado: propuesta del piloto; no hay bot conectado ni mensajes enviados por esta planificación.

## Corte inicial

Un bot de pruebas, un proceso consumidor, chats privados autorizados y mensajes de texto. Long polling evita exigir un endpoint público para el primer E2E. `getUpdates` y webhooks son alternativas excluyentes; `update_id` identifica updates, y `offset` confirma los anteriores. `sendMessage` acepta hasta 4096 caracteres tras parseo. Fuente consultada el 2026-10-06: [Telegram Bot API](https://core.telegram.org/bots/api#getupdates), [Update](https://core.telegram.org/bots/api#update), [sendMessage](https://core.telegram.org/bots/api#sendmessage).

El adapter normaliza la entrada y convierte la respuesta contextualizada a texto plano. Propuesta inicial: limitar la respuesta pública a un mensaje con indicador de truncamiento si hace falta; probar Unicode y límites antes de habilitar fragmentación. El core conserva el resultado completo sujeto a retención. Adjuntos, ediciones, callbacks, grupos y topics se clasifican como no soportados sin inferencia. Una futura entrada webhook reutilizará casos de uso/contratos y necesitará autenticación del webhook y política de ACK propias.

## Identidad y configuración

Configurar bot token solo en infraestructura y referenciarlo sin secreto; no registrar URLs de API que lo contengan. Binding administrado: cuenta del bot + chat privado + remitente → deployment/tenant/actor/conversation del producto. Validar chat y remitente; nunca tomar tenant o permisos del texto o username. Allowlist de prueba rechaza desconocidos antes de invocar modelos. Dos chats admitidos tienen conversaciones distintas y dos scopes de prueba no comparten contexto ni ledger.

Destinos externos quedan detrás de una referencia opaca resuelta por el adapter. Verificar que esa referencia pertenece al scope y a la interacción de origen antes de enviar. Un especialista nunca escoge chat_id ni destinatarios. No se publica ni reenvía a terceros.

## Idempotencia de entrada

Clave propuesta: `(deployment_id, tenant_id, channel_account_ref, external_event_id)`, con `external_event_id` mapeado desde update_id. Guardar hash canónico del mensaje normalizado y su identidad, no solo el texto. El mismo texto con otro evento es un nuevo turno; misma clave con payload distinto es conflicto.

| Estado de inbox | Evento repetido | Recuperación |
| --- | --- | --- |
| RECEIVED | Recuperar registro e IDs existentes | Procesar una sola vez mediante reserva atómica. |
| PROCESSING | No iniciar otra inferencia | Esperar resultado; al reiniciar marcar para revisión si no puede saberse si la inferencia ocurrió. |
| COMPLETED | Reutilizar outcome y entrega existente | No volver a generar ni agregar el mismo par al historial. |
| FAILED | Devolver estado seguro persistido | Reintento explícito según causa/policy; no una ejecución nueva por replay. |

Persistir cada update del lote en inbox antes de avanzar offset; los no soportados se registran como descartados. No confirmar por encima de un evento aún no persistido. El consumidor interno procesa registros durables, por lo que confirmar recepción no depende de que el LLM haya terminado. Probar caída entre persistencia y confirmación. Un lock/reserva por conversación evita que dos turnos lean y sobrescriban la misma revisión; conversaciones distintas pueden avanzar sin mezclar estado.

## Idempotencia de salida

Persistir una entrega por `(execution_id, response_id, destination_ref)` con unicidad, contenido público fijado y estado. La reserva de envío se realiza antes de llamar al proveedor.

| Estado | Significado | Acción |
| --- | --- | --- |
| PENDING | Nunca se inició el envío | Worker puede reservarlo. |
| SENDING | Intento en curso | Ningún segundo worker puede enviarlo. |
| SENT | Confirmación con referencia externa persistida | Replay no reenvía. |
| FAILED | Fallo conocido sin entrega | Reintentar solo si policy y clasificación del error lo permiten, con límite/deadline. |
| UNKNOWN_EFFECT | Timeout/desconexión o caída después de iniciar envío sin confirmación durable | No reenvío automático; registrar para inspección/reconciliación. |

El contrato consultado de sendMessage no ofrece una idempotency key del cliente; esta propuesta **no promete exactly-once externo**. La deduplicación local no elimina la ventana entre éxito remoto y confirmación local. Al reiniciar, una entrega SENDING sin resultado pasa a UNKNOWN_EFFECT. Mantener la respuesta pendiente de revisión evita duplicarla a costa de una posible entrega perdida. El piloto necesita un procedimiento de revisión que preserve el estado incierto cuando no se pueda confirmar; no simular éxito.

No reintentar el workflow entero porque falló la entrega. Respetar rate limits y deadlines mediante clasificación del adapter; cada retry seguro reutiliza la misma entrega lógica. Cero reintentos ciegos ante incertidumbre. El detalle general de side effects sigue abierto en ADR-021/023; estas reglas son un recorte propuesto para el piloto.

## Relación con tools y Policy

El gateway es un adapter de canal. La entrega de la respuesta desde Application es infraestructura de conversación, gobernada y registrada; no una API accesible desde el LLM. Si en el futuro un agente puede proponer «enviar mensaje», esa capability sí debe registrarse como Tool EXTERNAL_ACTION con ToolExecutorPort y ADR-005/021. No usar el gateway para eludir esa frontera.

En el piloto, PEP verifica scope, destino y permiso de responder antes del envío. DENY/INDETERMINATE no llaman al proveedor; REQUIRE_APPROVAL tampoco hasta que se implemente el lifecycle correspondiente. Un error al enviar un error no genera un bucle de nuevas respuestas.

## Prueba E2E propuesta

1. Superar Gate A con transporte Telegram simulado y otro canal fake.
2. Configurar bot de prueba, bindings, retención y almacenamiento durable; comprobar que no hay otro consumidor o webhook activo.
3. Ejecutar Telegram + FakeLLM: tres turnos, cambio de perfil, dos chats aislados y rechazo de remitente desconocido.
4. Reproducir el mismo update desde fixture/control de pruebas; reiniciar entre recepción y procesamiento y entre envío y confirmación simulada. No depender de que Telegram produzca un duplicado espontáneo.
5. Activar modelo/Decision Model reales solo con presupuesto disponible; medir calidad y latencias separadas de transporte.
6. Registrar IDs pseudonimizados, versiones, resultado y contadores de inferencia/entrega, sin tokens ni conversaciones crudas. Documentar parada, recuperación y borrado del estado de prueba.
