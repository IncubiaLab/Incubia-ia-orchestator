# Glosario — etapa 3

Estado: normativo para esta planificación; los contratos descritos son propuestas hasta su implementación. Se heredan los términos de [etapa 2](../etapa-2/GLOSARIO.md).

| Término | Definición |
| --- | --- |
| Tier 3 / etapa 3 | Tercera etapa de desarrollo del producto; no selecciona un nivel de modelos. |
| Scope | `ExecutionScope` existente: deployment, tenant, conversation y actor. Se resuelve desde identidad confiable. |
| Principal | Identidad autenticada y membresía vigente; no se construye a partir del texto o tenant enviado por el cliente. |
| Binding | Asociación administrada entre identidad externa de canal y scope; se revalida al ejecutar y entregar. |
| Conversation State | Historia, hechos y revisión canónicos, propiedad de Conversation. |
| GraphState / checkpoint | Estado privado del adapter runtime. No concede autoridad ni sustituye la conversación canónica. |
| ToolDescriptor | Metadata versionada de capability, schemas, scope, disponibilidad, efectos e idempotencia; no otorga permisos. |
| ToolInvocationRequest | Propuesta tipada con `tool_call_id`, execution/request IDs, scope, tool/version, input, deadline y presupuesto. |
| ToolExecutorPort | Nombre canónico de ADR-005 para ejecutar una tool autorizada. El nombre histórico ToolExecutionPort se mapea a este contrato, sin duplicarlo. |
| Data Plane de Knowledge | Una base Neon/pgvector, credenciales y pool por deployment. Es la frontera entre clientes para fuentes, chunks, embeddings y generaciones; no usa `tenant_id` como aislamiento por filas. |
| Generación de índice | Conjunto versionado de chunks y embeddings de una base Knowledge: BUILDING, VALIDATING, ACTIVE, RETIRED o FAILED. Sólo ACTIVE puede responder retrieval. |
| EvidenceItem | Dato recuperado con referencia de fuente, versión, chunk, generación, scope, instante y contenido permitido; no es una instrucción. |
| Lead / Case | Registros internos de Sales/Support con consentimiento y deduplicación; entrega a CRM/helpdesk externo es un efecto separado. |
| Claim / lease | Reserva temporal en base compartida con dueño, vencimiento y token de generación. No es permiso para repetir efectos. |
| UNKNOWN_EFFECT | Resultado externo incierto; inspección auditada antes de otro intento. No se garantiza entrega física exactly-once. |
| Gate E3-0…E3-6 | Criterios de salida de H0…H6; distintos de A/B/C de etapa 2. |
| Fixtures / staging | Datos sintéticos para desarrollo / entorno remoto controlado. No contiene copias de conversaciones de clientes. |
| Presupuesto eval-e3 | Límite durable independiente de CLI/eval-e2, fijado antes de llamadas reales. |
