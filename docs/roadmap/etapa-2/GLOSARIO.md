# Glosario — etapa 2

Estado: normativo para los documentos de etapa 2. Si un documento usa un término de forma distinta, prevalece esta tabla. Los nombres en `código` son los identificadores que se implementan tal cual.

## Identidad del especialista

| Término | Definición | No confundir con |
| --- | --- | --- |
| Specialty | Etiqueta pública existente (`Specialty.GENERAL/VENTAS/MARKETING`) que ve el usuario y usa la CLI. | Capability, agente o modelo. |
| Capability | Identificador estable de lo que puede pedirse (`conversation.assistance`, `sales.advice`, `marketing.planning`). Es la salida del routing. | Specialty: una capability se mapea a una specialty solo para mostrarla. |
| `SpecialtyProfile` | Configuración de comportamiento de un especialista: instrucciones, estilo, límites, presupuesto de contexto y `output_contract`. Versionada (`profile_id`, `profile_version`). | `AgentDescriptor`. |
| `AgentDescriptor` | Registro de descubrimiento (ADR-004): `agent_id`, `agent_version`, capabilities, scope, estado (`ENABLED`/`DISABLED`) y referencia al perfil. | Perfil: el descriptor no contiene instrucciones. |
| Agente | Par descriptor + perfil instanciado por bootstrap. En etapa 2 hay un agente por specialty. | Modelo LLM. |
| Modelo generativo | Modelo LLM que redacta la respuesta (`LLMPort`). Compartido por los tres perfiles. | Decision Model. |
| Decision Model | Clasificador que devuelve `RouteDecision` (`DecisionModelPort`). En etapa 2: mismo proveedor OpenAI con salida JSON estructurada. | `ModelRouterPort` (HEC-17, fuera de alcance). |

## Routing

| Término | Definición |
| --- | --- |
| `RouteDecision` | `{status, capability?, confidence, signals}`. `status ∈ {RESOLVED, AMBIGUOUS, UNSUPPORTED}`; `capability` solo si `RESOLVED`. |
| Discovery | Consulta que filtra descriptores por capability, scope y estado. Devuelve candidatos y no elige ninguno. |
| Selection | Regla determinista sobre los candidatos: mayor `priority` configurada y, en empate, menor `agent_id` lexicográfico y después mayor `agent_version`. |
| Baseline de keywords | Router actual (`application/router.py`). Se conserva solo como baseline de evaluación. |

## Contexto (tres cosas distintas)

| Término | Definición | Se envía al usuario |
| --- | --- | --- |
| Contexto de inferencia (`SpecialtyContext`) | Paquete que construye `ContextBuilder` para el LLM: instrucciones, hechos tipados, pares recientes, mensaje actual. | Nunca. |
| Conversación canónica | Estado persistido por `ConversationRepositoryPort`: turnos, hechos declarados y `revision` (entero de control optimista). | Nunca entera. |
| Contextualización de respuesta (`ContextualizedResponse`) | Contenido público neutral que produce `ResponseContextPort.contextualize`: texto/bloques, specialty, idioma, `reply_to`. | Sí, mediante el adapter del canal. |

«Revisión» designa siempre el número de versión de la conversación (`revision`). Para la revisión humana se usa «inspección manual».

## Ejecución e identificadores

| Término | Definición |
| --- | --- |
| Scope | El `ExecutionScope` existente: `deployment_id`, `tenant_id`, `conversation_id`, `actor_id`. No se crea otro tipo de scope. |
| Binding | Fila de configuración `(channel, channel_account_ref, external_chat_ref, external_sender_ref) → ExecutionScope`. Sin binding no hay procesamiento. |
| `request_id` | Una interacción entrante. Se genera una vez al aceptar el evento en inbox. |
| `execution_id` | Una ejecución lógica. Se genera una vez al aceptar el evento y se reutiliza en cualquier replay. |
| Clave de evento (inbox) | `(deployment_id, tenant_id, channel_account_ref, external_event_id)`. En Telegram, `external_event_id = str(update_id)`. En CLI, `cli:<uuid>` generado por la fachada. |
| `destination_ref` | Referencia opaca `<channel>:<binding_id>` que el adapter resuelve a `chat_id`. El core nunca ve `chat_id`. |

## Fiabilidad

| Término | Definición |
| --- | --- |
| Inbox | Tabla `inbox_events` con estados `RECEIVED → PROCESSING → COMPLETED / FAILED / NEEDS_INSPECTION`, más `DISCARDED` para tipos no soportados. |
| Outbox | Tabla `deliveries` con estados `PENDING → SENDING → SENT / FAILED / UNKNOWN_EFFECT`. |
| `UNKNOWN_EFFECT` | No se sabe si el proveedor entregó. Nunca se reintenta solo; se resuelve con el comando de inspección (ver TELEGRAM). |
| Runner | Proceso único, síncrono y de un solo hilo, que ejecuta el ciclo de TELEGRAM § Runner. |
| Gate A/B/C | Criterios de salida de H3, H4 y H5 respectivamente. |
| Presupuesto `eval-e2` | Cupo de llamadas reales para evaluación de etapa 2, separado del cupo CLI de 6 llamadas/mes. |
| Etapa 2 | Segunda etapa de desarrollo de este repo. No es un tier de modelos. |
