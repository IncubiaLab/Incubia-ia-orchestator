# Telegram — primer adaptador E2E

Estado: propuesta del piloto validada (H0); adapters en desarrollo (H4 activo); no hay bot conectado a producción ni flujo E2E completo.

## Corte inicial

Un bot de pruebas, un proceso consumidor, chats privados autorizados y mensajes de texto. Long polling evita exigir un endpoint público para el primer E2E. `getUpdates` y webhooks son alternativas excluyentes; `update_id` identifica updates, y `offset` confirma los anteriores. `sendMessage` acepta hasta 4096 caracteres tras parseo. Fuente consultada el 2026-10-06: [Telegram Bot API](https://core.telegram.org/bots/api#getupdates), [Update](https://core.telegram.org/bots/api#update), [sendMessage](https://core.telegram.org/bots/api#sendmessage).

El adapter normaliza la entrada y convierte la respuesta contextualizada a texto plano. Propuesta inicial: limitar la respuesta pública a un mensaje con indicador de truncamiento si hace falta; probar Unicode y límites antes de habilitar fragmentación. El core conserva el resultado completo sujeto a retención. Adjuntos, ediciones, callbacks, grupos y topics se clasifican como no soportados sin inferencia. Una futura entrada webhook reutilizará casos de uso/contratos y necesitará autenticación del webhook y política de ACK propias.

## Identidad y configuración

Configurar bot token solo en infraestructura y referenciarlo sin secreto; no registrar URLs de API que lo contengan. Binding administrado: cuenta del bot + chat privado + remitente → deployment/tenant/actor/conversation del producto. Validar chat y remitente; nunca tomar tenant o permisos del texto o username. Allowlist de prueba rechaza desconocidos antes de invocar modelos. Dos chats admitidos tienen conversaciones distintas y dos scopes de prueba no comparten contexto ni ledger.

Destinos externos quedan detrás de una referencia opaca resuelta por el adapter. Verificar que esa referencia pertenece al scope y a la interacción de origen antes de enviar. Un especialista nunca escoge chat_id ni destinatarios. No se publica ni reenvía a terceros.

## Idempotencia de entrada

Clave propuesta: `(deployment_id, tenant_id, channel_account_ref, external_event_id)`, con `external_event_id` mapeado desde update_id. Guardar hash canónico del mensaje normalizado y su identidad, no solo el texto. El mismo texto con otro evento es un nuevo turno; misma clave con payload distinto es conflicto.

| Estado de inbox | Evento repetido | Transición permitida |
| --- | --- | --- |
| RECEIVED | Devolver IDs existentes; no insertar | → PROCESSING mediante `UPDATE ... WHERE state='RECEIVED'` (afecta 1 fila o no se procesa). |
| PROCESSING | No iniciar otra inferencia | → COMPLETED / FAILED. Al arrancar el runner, todo PROCESSING pasa a NEEDS_INSPECTION (no se sabe si hubo llamada al LLM). |
| COMPLETED | Reutilizar outcome y entrega existente | Terminal. No regenera ni agrega el par al historial. |
| FAILED | Devolver estado seguro persistido | Terminal para replay. Solo `incubia-bot inspect --retry <event>` lo devuelve a RECEIVED, y solo si `error_code` es transitorio. |
| NEEDS_INSPECTION | No procesar | Solo por comando de inspección: → RECEIVED (reprocesar) o → FAILED (cerrar). |
| DISCARDED | No procesar | Terminal. Tipos no soportados (adjuntos, ediciones, callbacks, grupos), remitente sin binding. |

Mismo `external_event_id` con `payload_hash` distinto → `IdempotencyConflict`; el evento no se procesa y se registra como incidente.

## Runner (decisión H0: loop síncrono único)

Un proceso, un hilo y sin asyncio. Cada iteración hace, en este orden:

1. `getUpdates(offset=last_offset+1, timeout=30, allowed_updates=["message"])`.
2. En una transacción: insertar cada update en `inbox_events` (RECEIVED o DISCARDED) y guardar `last_offset = max(update_id)` en `runner_state`.
3. Procesar en orden de `received_at` cada evento RECEIVED: reservar → construir contexto → runtime → `contextualize` → transacción {turno + outcome + `deliveries` PENDING + inbox COMPLETED}.
4. Despachar `deliveries` PENDING (y FAILED con reintento vencido): marcar SENDING y hacer commit → `sendMessage` → SENT / FAILED / UNKNOWN_EFFECT.

El offset se confirma ante Telegram en la siguiente llamada a `getUpdates`, después del commit del paso 2. Una caída entre los pasos 2 y 3 deja eventos RECEIVED que se procesan al reiniciar. La serialización por conversación es consecuencia del hilo único. El control optimista (`revision`) sigue existiendo para detectar escrituras desde la CLI u otro proceso. Un solo consumidor por bot: lock de archivo exclusivo `<db>.runner.lock`; además, un HTTP 409 de `getUpdates` detiene el runner con un error explícito.

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

Clasificación de errores de `sendMessage` (implementada en el adapter):

| Respuesta | Estado | Reintento |
| --- | --- | --- |
| 200 `ok:true` | SENT, guarda `message_id` | — |
| 429 con `retry_after` | FAILED transitorio | `next_attempt_at = now + retry_after`. |
| 5xx o error de conexión antes de enviar el request | FAILED transitorio | Backoff 2/8/30 s; máximo 3 intentos y deadline de 10 min desde `created_at`. Después, FAILED terminal. |
| 400/403 (chat inválido, bot bloqueado) | FAILED terminal | No. |
| Timeout de lectura o desconexión después de enviar | UNKNOWN_EFFECT | No. |

Inspección manual: `incubia-bot inspect` lista los eventos NEEDS_INSPECTION y las entregas UNKNOWN_EFFECT. `--mark-sent <id>` y `--mark-failed <id>` cierran una entrega tras verificarla en el chat de prueba. `--resend <id>` crea un intento nuevo y deja constancia de la acción y del operador. Nada de esto se ejecuta automáticamente.

No reintentar el workflow entero porque falló la entrega. Cada retry seguro reutiliza la misma entrega lógica. Cero reintentos ciegos ante incertidumbre. Formato de salida: texto plano sin `parse_mode`. Si el texto supera 4096 caracteres, se trunca a 4090 y se añade « […]»; la fragmentación queda fuera de etapa 2. El detalle general de side effects sigue abierto en ADR-021/023; estas reglas son un recorte propuesto para el piloto.

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
