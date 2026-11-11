# How-to — implementación técnica de etapa 3

Fecha de revisión: 2026-10-15. Guía de implementación E3-01…15. Algunas tareas tienen slices y evidencia parcial; el estado vigente está en [PROGRESS](PROGRESS.md) y [VERIFICACION](VERIFICACION.md). Esta guía no acredita cierre de gates.

Leer primero [dessing.md](dessing.md) para entender contratos y responsabilidades. [PLAN-E3](PLAN-E3.md) conserva el detalle de tareas; [GOALS](GOALS.md) y [VERIFICACION](VERIFICACION.md) gobiernan aceptación.

## 1. Preparar el entorno y establecer el baseline

Desde la raíz del repositorio, revisar cambios locales antes de editar:

```bash
git status --short
.venv/bin/python --version
```

El proyecto requiere Python ≥3.12. Si no existe `.venv`, seguir la instalación de [README](../../../README.md). Para esta implementación, reutilizar el entorno existente y las versiones declaradas en [pyproject.toml](../../../pyproject.toml); el driver PostgreSQL y las migraciones SQL versionadas ya están incorporados. Registrar las dependencias nuevas también en el mecanismo de instalación reproducible del proyecto.

Comandos existentes para acreditar el punto de partida durante la implementación:

```bash
.venv/bin/python -m pytest tests/test_boundaries.py tests/test_cli_offline.py -q
.venv/bin/python -m pytest tests/integration/test_sqlite_ledger.py tests/integration/test_gate_a_e2e.py tests/integration/test_telegram_runner.py -q
.venv/bin/python -m incubia_orchestrator.interfaces.cli.main chat --fake -m "quiero vender"
```

Registrar el resultado real antes de continuar. Estos comandos no fueron ejecutados al redactar esta guía. El bloqueo de red de [tests/conftest.py](../../../tests/conftest.py) afecta también conexiones TCP locales; no basta añadir un marker para conectar PostgreSQL.

## 2. Resolver el primer incremento: E3-01 y E3-02

Actualizar [PROGRESS](PROGRESS.md) con baseline, decisiones D1–D10, responsables y evidencia E2. Gate A consta cerrado; B/C mantienen su condición hasta tener resultados completos. Contratos y trabajo offline E3 pueden avanzar mientras se completan esas evidencias.

Antes de implementar Neon, realizar estos cambios en orden:

1. Inventariar llamadas públicas al ledger desde Telegram y operaciones del repositorio conversacional. Definir tipos propios para reserva, evento aceptado, claim y finalización.
2. Extraer `ConversationLedgerPort` en la ruta propuesta `modules/conversation/ports/ledger.py`. Sustituir el acceso `ledger._connection` del runner por una lectura tipada del evento que incluya request/execution IDs y scope persistidos. Conservar la aceptación atómica del update —o su descarte justificado— junto con el cursor Telegram; avanzar el cursor exige haber persistido esa disposición.
3. Introducir `Principal` y resolución de scope en Identity/Tenant. El binding administrado resuelve identidad externa; membresía y policy determinan qué recursos puede usar.
4. Modificar el contrato de entrada de Application para recibir la identidad de ejecución reservada. Un replay conserva `request_id` y `execution_id`; un nuevo intento físico recibe un `attempt_id` distinto.
5. Definir una finalización atómica de Conversation: revisión, turno, outcome, inbox y outbox en el mismo commit. Implementarla primero en SQLite y verificarla contra el fake/contrato.
6. Componer la ruta nueva en bootstrap y probar CLI/Telegram. La presencia de `HandleInbound` en el árbol no demuestra que las entradas públicas lo utilicen.

Las firmas finales se fijan en E3-02; los nombres propuestos no obligan a conservar métodos que exponen detalles SQL. Mantener `ConversationRepositoryPort` para lectura de contexto; evitar que `append_turn` y el commit del ledger incorporen dos veces el mismo turno.

**Salida revisable:** contratos versionados, runner sin SQL privado, ejecución con IDs reservados y prueba de caída antes/después del commit final. Detalles de las brechas actuales en [dessing.md](dessing.md).

## 3. Construir persistencia compartida: E3-03…05

### 3.1 Adapter y esquema

Implementar PostgreSQL en `modules/conversation/adapters/persistence/postgres/` contra el contrato de E3-02. El slice usa `psycopg` y migraciones SQL versionadas; mantener sus versiones y registrar cambios en D1. Domain/Application siguen consumiendo valores propios.

Crear migraciones por incremento funcional: identidad/bindings y Conversation primero; tools/audit, Knowledge y lead/case al abrir sus tareas. Cada migración incluye versión, constraints, índices por consultas reales y prueba de actualización desde el esquema anterior. Ejecutar migraciones desde un paso operativo único; evitar que cada réplica modifique el schema al arrancar.

Diseñar claves compuestas y relaciones scoped según [dessing.md](dessing.md). El esquema SQLite actual no sirve como evidencia de aislamiento PostgreSQL. Las filas sin identidad suficiente para migrarlas se ponen en cuarentena con causa; no se completa el tenant o conversation con un valor arbitrario.

### 3.2 Configuración y conexiones

Convención de variables para E3. La plantilla Neon, el runner opt-in y el adapter H1 existen; la activación productiva sigue pendiente:

| Configuración | Uso |
| --- | --- |
| `DATABASE_URL` | Conexión de runtime, con rol limitado y TLS. |
| `INCUBIA_MIGRATION_DATABASE_URL` | Conexión directa y rol de migración, disponible solo al proceso operativo. |
| `INCUBIA_E3_DB_POOL_MAX` | Máximo local por proceso; elegir según concurrencia y límite total del despliegue. |
| Config E3 versionada | Backend, límites de consultas/turnos, deadlines y referencias opacas de credenciales. |

Comprobar la carga explícita de configuración y su validación al preparar operación productiva. `scripts/e3/neon_h1.py` preparó roles SQL, grants mínimos y el archivo local ignorado según ADR-ORCH-027. No imprimir DSN, contraseña ni tokens para diagnosticar conectividad. Una URL con `-pooler` corresponde a conexión agrupada; Neon recomienda conexión directa para migraciones o funciones de sesión. Consultar [conexión oficial de Neon](https://github.com/neondatabase/website/blob/main/content/docs/get-started/connect-neon.md).

Verificar schema/rol con una consulta mínima antes de aceptar trabajo. Limitar conexiones agregadas entre procesos, esperar pool dentro del deadline y liberar conexiones antes de LLM/HTTP. Registrar región/plan y capacidad de restore del entorno usado; la selección del proveedor no acredita su configuración.

### 3.3 Contrato, concurrencia y restore

Usar los mismos escenarios de contrato para SQLite y PostgreSQL. PostgreSQL necesita además dos conexiones/procesos compitiendo por evento y conversación, y un dueño vencido intentando finalizar. Verificar que solo el dueño vigente modifica el estado y que el commit parcial deja cero cambios.

El runner `scripts/e3/run_neon_h1.py` habilita sólo casos `@pytest.mark.neon` con flags explícitos, branch guard, rol, TLS y endpoint directo/pooled validados; `conftest.py` mantiene bloqueadas las demás pruebas. La campaña ampliada con `004`/`005` pasó 7 checks y el smoke de import vacío fue idempotente. Falta restore con filas, RPO/RTO y equivalencia completa de contratos.

Ensayar export/import idempotente sobre datos sintéticos y restauración aislada según [RUNBOOK](RUNBOOK.md). El corte inicial usa pausa de escrituras y una autoridad única. Comparar hashes, revisiones, IDs, inbox/outbox y offsets; reconciliar entregas inciertas antes de reactivar dispatch. E3-1 requiere evidencia sobre Neon, incluyendo roles y restore.

## 4. Completar identidad y autorización: E3-06

Resolver scope desde binding y membresía vigentes. Para la primera entrada HTTP, si se habilita, resolver la identidad mediante el proveedor elegido en D3. Limitar el lookup previo a conocer el tenant a un contrato de identidad específico; no conceder al runtime acceso general a todas las organizaciones.

Aplicar policy antes de leer recursos, llamar tools/retrieval y entregar. Revalidar después de esperas; propagar una revocación a las cachés de permisos. El binding almacenado y el scope del evento deben coincidir: un cambio de binding durante el procesamiento no mueve el evento a otra conversación.

Escenarios mínimos: dos tenants y dos actores por tenant; conversación ajena dentro del mismo tenant; membresía revocada tras encolar; rol insuficiente; tenant indicado en texto; respuesta encolada cuyo destinatario perdió acceso. E3-2 usa discovery fake antes de RAG; E3-4 repite el aislamiento sobre el store real.

## 5. Implementar la primera herramienta READ: E3-07/08

Seguir [TOOLING](TOOLING.md) y ADR-005:

1. Definir `ToolDescriptor`, schemas concretos, `ToolInvocationRequest` y resultado discriminado. Elegir un `tool_id` estable para `business.catalog.lookup` y un fake determinista.
2. Implementar registry/discovery con filtros de deployment/tenant, versión, enabled y compatibilidad; selección estable separada de policy.
3. Implementar el executor de Application que valida propuesta, recurso, autoridad, deadline y presupuesto; persiste intención/audit y llama al adapter autorizado.
4. Implementar un adapter HTTP usando el cliente ya disponible y transporte simulado. Configurar base URL por operador, validar redirects y limitar tamaño de respuesta.
5. Registrar intentos, outcome y evidencia; solo entonces incorporarlos a contexto/respuesta. Habilitar una lectura controlada del sistema elegido al acreditar gates de datos/identidad y disponer del acceso correspondiente.

Probar DENY, INDETERMINATE y REQUIRE_APPROVAL con contador de adapter igual a cero. Agregar casos de payload/schema inválido, cuota agotada, credencial revocada, timeout y contenido remoto que intenta dar instrucciones. El proveedor concreto sigue D5; no inventar una API de CRM o catálogo.

Los retries se implementan en una sola capa. El límite propuesto de dos intentos READ incluye el inicial. El deadline de tool está acotado por el restante del turno; no sumar un nuevo presupuesto completo al pasar de nodo.

## 6. Incorporar Knowledge y generación fundamentada: E3-09…11

Definir puertos y fake antes de pgvector. Crear corpus sintético y dataset con consultas, scope y fuentes relevantes esperadas; congelar val según [KNOWLEDGE](KNOWLEDGE.md). ADR-010 ya selecciona Neon/PostgreSQL + pgvector y una base por deployment; E3-10 fija el modelo/dimensión de embeddings y acredita búsqueda exacta frente a HNSW, con versiones registradas.

Implementar ingestión por hash/version, chunks y generación; una generación nueva es invisible hasta completarla y hacer el swap activo. Resolver la base, credenciales y pool desde `deployment_id` confiable, nunca desde texto, prompt o input de usuario. Revocar una fuente la excluye de retrieval y contexto pendiente antes de generar/entregar, aunque el borrado físico siga otro ciclo. Cache keys incluyen deployment, generación, policy y versiones de fuente/modelo.

En Application, combinar evidencia de READ y retrieval con el perfil seleccionado. Definir un contrato de generación que transporte realmente las instrucciones y EvidenceItems permitidos; no asumir que añadirlos a `ContextBuilder` los hace llegar al adapter LLM. Los nodos del grafo reciben esos servicios por composición.

Salida pública: hechos sustentados, referencias accesibles y abstención si no hay evidencia suficiente. Respetar presupuesto global de contexto y tamaño de tools/chunks. Mantener fuera de la respuesta instrucciones privadas, secretos y referencias que el actor no puede consultar.

Medir recall/abstención, afirmaciones respaldadas y referencias válidas usando los denominadores de GOALS. Cero fuga tiene prioridad sobre el score promedio. Registrar tanto intentos fallidos como escenarios exitosos.

## 7. Completar operación y flujos internos: E3-12…15

Instrumentar eventos desde E3-08 y consolidarlos en E3-12. Cada policy/tool/retrieval/outcome conserva correlación. Audit crítico durable falla de forma cerrada; el exportador de métricas utiliza recursos acotados y no controla el commit del producto.

Ensayar shutdown sin aceptar nuevo trabajo, recuperación de claims y entregas inciertas, y readiness frente a DB no disponible. Medir carga separando sesiones activas y peticiones simultáneas. Incluir procesos, RPS, n, cola, pool, p50/p95/p99 y errores. D8 define hosting/API/workers con esos resultados.

Para lead/case, implementar primero repositorios y casos de uso internos con permiso y clave lógica única. El lead exige consentimiento explícito; el case se crea conforme a la regla autorizada de fallback del plan. Verificar replay, tenant/actor ajeno y revocación. Una respuesta de éxito se emite después del commit correspondiente; consultar el registro existente al repetir el evento.

Finalmente ejecutar evaluación real con `eval-e3` y límites definidos. Registrar E2E CLI/Telegram, G1–G9 y decisión de release según [VERIFICACION](VERIFICACION.md). Varios scripts `scripts/e3/*` ya existen; `evals/run_e3.py` y la campaña de release siguen pendientes. Registrar comandos exactos al ejecutarlos.

## 8. Rutina por tarea y revisión técnica

Para cada E3-xx: leer sus dependencias → escribir contrato/invariantes → comprobar el fallo relevante → implementar adapter/caso de uso → verificar comportamiento → integrar en bootstrap → registrar evidencia. Las pruebas deben cubrir fallos, scope y recuperación; evitar pruebas que solo repiten asignaciones internas.

| Antes de dar una tarea por terminada | Evidencia |
| --- | --- |
| Contrato con estados/errores/versiones definidos | Pruebas de éxito, rechazo y compatibilidad. |
| Acceso scoped y policy en el punto de uso | Casos negativos con cero efectos. |
| IDs, claims y commit consistentes | Replay/carrera/caída conservan una incorporación lógica. |
| Configuración reproducible y recursos acotados | Dependencias fijadas, límites validados y secretos ausentes. |
| Integración con entradas existentes | CLI/Telegram usan el caso de uso y contratos previstos. |
| Gate respaldado | Informe fechado con commit, entorno, resultados y limitaciones. |

Ejecutar pruebas relevantes tras cada cambio y la suite offline completa al integrar el slice. No ejecutar campañas remotas por defecto. Registrar progreso por evidencia, sin marcar completo un gate solo por añadir código o documentos.

## 9. Mapa de consulta

La carpeta contenía 14 documentos de planificación al crear estas guías; se incorporaron todos como fuentes.

| Fuente | Consultar para |
| --- | --- |
| [ROADMAP](ROADMAP.md), [IMPLEMENTACION](IMPLEMENTACION.md), [PLAN-E3](PLAN-E3.md) | Hitos, orden de tareas, rutas y dependencias. |
| [BASE](BASE.md), [GLOSARIO](GLOSARIO.md) | Ownership, contratos e identificadores. |
| [AGENTES](AGENTES.md), [TOOLING](TOOLING.md), [KNOWLEDGE](KNOWLEDGE.md) | Capacidades, evidencia y límites por flujo. |
| [GOALS](GOALS.md), [VERIFICACION](VERIFICACION.md) | Métricas, pruebas y cierre de gates. |
| [AUTOPLAN-REVIEW](AUTOPLAN-REVIEW.md), [LINEAR-ADR](LINEAR-ADR.md) | Decisiones pendientes y alcance de las fuentes. |
| [RUNBOOK](RUNBOOK.md), [PROGRESS](PROGRESS.md) | Operación, recuperación y estado acreditado. |

## 10. HOWTO del RAG IncubiaLab

Actualizado: 2026-10-21. Esta sección guía el feature prioritario en tres entregas de [GOALS](GOALS.md#feature-rag-incubialab-tres-etapas-y-tres-entregas). Las secciones anteriores conservan el recorrido global; sus descripciones históricas no sustituyen una inspección del código. El diseño y las fuentes oficiales están en [dessing](dessing.md#11-diseño-del-rag-incubialab). Los componentes nuevos descritos aquí están **por implementar**.

### 10.1 Etapa 1: acceso, conexión y Markdown — RAG-V1

1. Registrar baseline: `git status --short`, versiones de Python/dependencias y pruebas relevantes. Inspeccionar `modules/knowledge` bajo `src/incubia_orchestrator`, sus migraciones y bootstrap; registrar qué capacidades ya existen. No leer ni copiar secretos a informes.
2. Verificar metadatos de la raíz [IncubiaLab](https://drive.google.com/drive/folders/1IiwcAQpeY-OeK9EwkS9oJnfMxw653kun) con la identidad que usará el backend. Un 404 significa acceso no acreditado; no demostrar carpeta vacía con una lista vacía. Elegir OAuth de una cuenta dedicada o cuenta de servicio con acceso compartido explícito; el conector del chat no proporciona automáticamente credenciales a Python. Definir binding verificable entre actor interno e identidad/grupos de Drive.
3. Crear adapter Drive de sólo lectura. Elegir scopes mínimos que permitan el corpus: `drive.file` sólo cubre archivos autorizados para la app y no garantiza leer una carpeta preexistente completa; si se necesita `drive.readonly`, restringir además la raíz en la aplicación. Recorrer hijos con `files.list`, filtro `'<folder_id>' in parents and trashed = false`, paginación completa, conjunto de visitados y límites de profundidad/documentos. En unidades compartidas configurar parámetros de soporte y `driveId` según API. No seguir shortcuts fuera de raíz; resolver su destino y verificar pertenencia/permiso o excluir con causa. Referencias: [scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [permisos](https://developers.google.com/workspace/drive/api/guides/manage-sharing).
4. Inventariar ID, MIME, nombre, padres, versión observada, modifiedTime, tamaño disponible, clasificación y estado ACL. Congelar 10–20 documentos representativos: texto, tabla y presentación cuando existan. Revisar todas las páginas/hojas del original; incluir fixtures sintéticos separados para formatos ausentes. Los correos y ACL detalladas permanecen en almacenamiento privado.
5. Confirmar proyecto, branch y base Knowledge de Neon. Registrar identidad de entorno sin DSN. Preparar rol migrador, ingestor y runtime con grants separados; runtime sin DDL/escrituras de ingestión, ingestor sin privilegios de propietario, ningún runtime con superuser/BYPASSRLS. Comprobar TLS, versión PostgreSQL/vector, migraciones y permisos positivos/negativos. La extensión `vector` la habilita el migrador. Pool runtime acotado; conexión directa para migraciones y backup. [Neon pgvector](https://neon.com/docs/extensions/pgvector), [pooling](https://neon.com/docs/connect/connection-pooling).
6. Exportar Docs a `text/markdown`, Sheets a XLSX para conservar todas las hojas y Slides a PPTX. Descargar binarios por API autenticada. CSV sólo representa la primera hoja de una exportación de Sheets. `files.export` tiene límite documentado de 10 MB; archivos excedidos quedan pendientes de ruta específica, nunca truncados. [Formatos](https://developers.google.com/workspace/drive/api/guides/ref-export-formats), [descarga](https://developers.google.com/workspace/drive/api/guides/manage-downloads).
7. Implementar `scripts/e3/prepare_knowledge_markdown.py` como CLI del conversor. Entradas: archivo local, directorio de salida, deployment, source_id, versión observada y URL original. Salidas: `document.md` y `manifest.json`. Validar MIME/extensión, archivo regular sin symlink, tamaño de entrada/salida, UTF-8 y extracción no vacía. Propuesta inicial: máximo 25 MB por archivo; configurar límites de expansión ZIP, memoria y tiempo para Office. Usar MarkItDown con plugins desactivados para DOCX/PPTX/XLSX/PDF; aislar proceso sin credenciales ni salida de red. PDFs escaneados/tablas complejas requieren revisión y ruta OCR explícita, con presupuesto si usa proveedor remoto. [Repositorio Microsoft](https://github.com/microsoft/markitdown).
8. Mantener encabezados, listas, tablas, código y referencias de página/hoja/diapositiva cuando el extractor las proporcione. No inventar localizadores. Manifiesto: hashes SHA-256 original/Markdown, versión convertidor/pipeline, fuente/versión, fecha, tipo, revisión de extracción y ACL; `ingest_ready=false` hasta aprobar ambas. Comparar metadata antes/después de descargar: si cambió, reintentar con límite o poner en cuarentena.
9. Mostrar original frente a Markdown, inventario, preflight y casos de rechazo. Entregar RAG-V1 y registrar decisión del usuario antes de V2.

Contrato ilustrativo del conversor, no comando disponible en este checkout:

```text
prepare_knowledge_markdown.py INPUT --output-dir PRIVATE_DIR
  --deployment-id DEPLOYMENT --source-id DRIVE_FILE_ID
  --source-version OBSERVED_VERSION --source-url ORIGINAL_URL
```

No instalar `latest` durante producción: elegir release compatible de MarkItDown, fijar versión/hash y dependencias en el lock, probar corpus y registrar licencia. Las páginas oficiales describen versiones actuales; la integración debe verificarse contra las versiones fijadas en este repositorio.

### 10.2 Etapa 2: contratos, chunks, ingestión y respuesta — RAG-V2

1. Extender `knowledge/domain.py`, `ports.py` e `application/ingest.py`: documento/version separado de chunks. Mantener compatibilidad del corpus sintético mediante adapter de un chunk. Añadir migración aditiva posterior a `001_knowledge.sql` y `002_hnsw_opt_in.sql`; probar upgrade en base aislada antes de activar nuevos lectores.
2. Fijar modelo, revisión, dimensión, normalización y tokenizer efectivos en un fingerprint. El modelo local candidato ya tiene adapter; su ficha indica 384 dimensiones y secuencia de 128 tokens. Confirmar configuración real ONNX/FastEmbed. Empezar experimentos con cuerpos de 80–96 tokens y overlap de 8–16, reservando encabezados y tokens especiales. Son hipótesis para dev, no valores aprobados. Cumplir también 4096 bytes por EvidenceItem. [Ficha del modelo](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
3. Separar Markdown por estructura y luego por presupuesto real del tokenizer. Repetir encabezados de tabla en cada bloque; dividir filas largas de forma explícita conservando clave de fila, no cortar celdas silenciosamente. Preservar breadcrumb y offset; para bloques de código largos registrar continuidad. Cada chunk tiene ordinal, hash, versión del chunker y localizador. Rechazar cualquier truncación implícita del embedder; verificar token count final incluyendo prefijos.
4. Producir embeddings en lotes acotados fuera de transacciones SQL. Validar dimensión, valores finitos, cardinalidad y fingerprint. Cachear por hash del texto efectivo + fingerprint; no compartir contenido privado entre deployments. Si cambia modelo, regenerar corpus y vector de consulta juntos. Reservar gasto durable antes de proveedores remotos; no asumir presupuestos antiguos disponibles.
5. Crear generación BUILDING, escribir lotes idempotentes, validar manifiesto completo y publicar con lock/CAS en transacción corta. Un delta de Drive debe reconstruir un snapshot lógico completo, incluyendo documentos sin cambios; no publicar sólo los modificados. La eliminación del último documento debe permitir generación vacía válida. Un fallo mantiene activa la generación anterior.
6. Resolver scope desde Identity y DSN desde Control Plane. Aplicar ACL de documento y estado de autorización vigente en SQL antes del top-k. Usar búsqueda exacta como baseline; habilitar HNSW sólo después de comparar recall y latencia con filtros reales, versión de extensión compatible y plan SQL observado. Ajustar umbral de abstención únicamente con dev; no es una probabilidad. [pgvector: filtros](https://github.com/pgvector/pgvector#filtering).
7. Integrar EvidenceItems en `grounded_workflow.py`, `grounded_response.py`, `response_context.py` y `bootstrap/e3_grounded.py`. El probe y el runtime deben usar el mismo fingerprint del índice. Vincular cita a source/version/chunk autorizado; no usar URLs privadas como `public_ref` sin ampliar el contrato. Verificar autorización antes de mandar texto al LLM y antes de entregar, descartando respuesta si perdió acceso.
8. Congelar dev/val, manifest/modelo/config, ejecutar pruebas negativas y métricas de GOALS. Tratar títulos/enlaces como información protegida. Mostrar respuesta respondible, abstención y mismo prompt con actor sin acceso. Entregar RAG-V2 con rúbrica y decisión explícita.

Pruebas existentes útiles como regresión, ejecutables desde la raíz con el entorno instalado:

```bash
.venv/bin/python -m pytest tests/unit/test_knowledge_contracts.py tests/integration/test_grounded_conversation.py tests/test_boundaries.py -q
```

Añadir pruebas de comportamiento para multichunk, pérdida a mitad de ingestión, publicación concurrente, corpus vacío, incompatibilidad de modelo, SQL ACL previo a top-k y revocación durante generación. Las campañas Neon requieren su harness opt-in y entorno aislado; no desactivar globalmente el bloqueo de red de tests.

### 10.3 Etapa 3: sincronización y operación — RAG-V3

1. Obtener cursor inicial antes del inventario completo; tras el inventario, consumir cambios desde ese cursor para cubrir carreras. Persistir cada página como trabajos durables e idempotentes y avanzar cursor en la misma transacción. El worker puede procesarlos después; el cursor acredita trabajos durables, no indexación terminada. Guardar `newStartPageToken` al agotar páginas; si el cursor no puede recuperarse, reconciliar inventario completo. [Drive Changes](https://developers.google.com/workspace/drive/api/guides/manage-changes).
2. Revalidar raíz/ancestros, papelera, bajas, movimientos y acceso en cada cambio. El feed no equivale a un filtro recursivo de carpeta ni resuelve toda autorización de grupos; añadir reconciliación periódica y verificación de permisos. 403/404 sobre una fuente conocida la inhabilita preventivamente. Timeout global no borra corpus: suspende fuentes con autorización vencida y genera alerta.
3. Fijar propietario del job mediante lease/fencing; retries sólo para errores transitorios, con backoff/jitter, Retry-After y límite. Registrar fallo permanente/cuarentena sin saltarlo silenciosamente. Deduplicar por fuente/versión/hash/pipeline; registrar versión ACL aparte de contenido.
4. Invalidar cachés por deployment, actor/tenant, versión de policy/ACL, generación y modelo. Medir la ventana de revocación de GOALS, incluyendo grupos y permisos heredados. Si no se puede resolver membresía de un grupo, denegar los grants dependientes de él; el acceso amplio del ingestor no autoriza a los usuarios finales.
5. Instrumentar importación, cuarentena, lag, cambios pendientes, tokens, costos, p50/p95/p99, errores, cola y pool. Correlacionar request/execution/source/generation en audit con campos acotados. No usar IDs privados como labels de métricas. Audit crítico durable; exportador de métricas desacoplado.
6. Simular Drive 429/403, caída DB/embedding, commit incierto, SIGTERM y restart. Verificar persistencia de jobs/cursor y ausencia de generación parcial visible. Repetir después de revocar una fuente durante respuesta y con outbox pendiente.
7. Ensayar rollback de índice conservando revocaciones actuales y restore en base aislada. No reabrir lectura restaurada hasta reconciliar ACL con Drive. Medir RPO/RTO, verificar hashes, versiones y claves idempotentes. Definir retención y eliminación de Markdown, chunks, cachés, backups y ramas; una rama de Neon puede contener datos privados. [Branching Neon](https://neon.com/docs/introduction/branching).
8. Ejecutar perfil acordado ≥10 minutos, separar arranque frío/caliente, confirmar límites monetarios y regresión CLI/Telegram. Preparar runbook con activar/desactivar RAG, diagnóstico sin secretos, reintento, reindex, rollback y restore. Entregar RAG-V3; sólo después de aceptación retomar backlog global.

### 10.4 Paquete revisable por entrega

| Campo del reporte | Contenido requerido |
| --- | --- |
| Identidad | Entrega, fecha, responsable, commit/diff, entorno y schema. |
| Reproducibilidad | Versiones fijas, fingerprint, hashes del corpus/config y comandos realmente ejecutados. |
| Calidad | n, denominadores de GOALS, fallos completos y revisión manual; dev separado de val. |
| Operación | Latencia/errores/costos conocidos, alcance del ensayo y límites pendientes. |
| Decisión | `lista_para_validacion` o `requiere_cambios`; sólo aceptación explícita pasa a `validada`. |

Los nombres de scripts nuevos y tablas del diseño son contratos propuestos. No presentar pseudocomandos, reportes futuros ni una prueba sintética como ejecución real sobre IncubiaLab.
