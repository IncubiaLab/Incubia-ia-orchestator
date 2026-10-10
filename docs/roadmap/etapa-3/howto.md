# How-to — implementación técnica de etapa 3

Fecha: 2026-10-07. Guía para implementar E3-01…15 sobre el código existente. Los comandos de baseline usan archivos actuales; las APIs, rutas y comandos nuevos se señalan como propuestas. Esta guía no acredita implementación ni cierre de gates.

Leer primero [dessing.md](dessing.md) para entender contratos y responsabilidades. [PLAN-E3](PLAN-E3.md) conserva el detalle de tareas; [GOALS](GOALS.md) y [VERIFICACION](VERIFICACION.md) gobiernan aceptación.

## 1. Preparar el entorno y establecer el baseline

Desde la raíz del repositorio, revisar cambios locales antes de editar:

```bash
git status --short
.venv/bin/python --version
```

El proyecto requiere Python ≥3.12. Si no existe `.venv`, seguir la instalación de [README](../../../README.md). Para esta implementación, reutilizar el entorno existente y las versiones declaradas en [pyproject.toml](../../../pyproject.toml); añadir driver/migrador PostgreSQL cuando E3-03 resuelva compatibilidad. Registrar las dependencias nuevas también en el mecanismo de instalación reproducible del proyecto.

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

Implementar PostgreSQL en `modules/conversation/adapters/persistence/postgres/` contra el contrato de E3-02. Seleccionar driver y herramienta de migración, fijar sus versiones y registrar el motivo en D1. Domain/Application siguen consumiendo valores propios.

Crear migraciones por incremento funcional: identidad/bindings y Conversation primero; tools/audit, Knowledge y lead/case al abrir sus tareas. Cada migración incluye versión, constraints, índices por consultas reales y prueba de actualización desde el esquema anterior. Ejecutar migraciones desde un paso operativo único; evitar que cada réplica modifique el schema al arrancar.

Diseñar claves compuestas y relaciones scoped según [dessing.md](dessing.md). El esquema SQLite actual no sirve como evidencia de aislamiento PostgreSQL. Las filas sin identidad suficiente para migrarlas se ponen en cuarentena con causa; no se completa el tenant o conversation con un valor arbitrario.

### 3.2 Configuración y conexiones

Convención de variables para E3. La plantilla Neon y el runner opt-in existen; el adapter/runtime todavía no consume los DSNs Neon hasta completar E3-03:

| Configuración | Uso |
| --- | --- |
| `DATABASE_URL` | Conexión de runtime, con rol limitado y TLS. |
| `INCUBIA_MIGRATION_DATABASE_URL` | Conexión directa y rol de migración, disponible solo al proceso operativo. |
| `INCUBIA_E3_DB_POOL_MAX` | Máximo local por proceso; elegir según concurrencia y límite total del despliegue. |
| Config E3 versionada | Backend, límites de consultas/turnos, deadlines y referencias opacas de credenciales. |

El loader actual de bootstrap no carga estas variables desde `.env`; añadir soporte explícito y pruebas de configuración en E3-03. `scripts/e3/neon_h1.py` preparó roles SQL, grants mínimos y el archivo local ignorado según ADR-ORCH-027. No imprimir DSN, contraseña ni tokens para diagnosticar conectividad. Una URL con `-pooler` corresponde a conexión agrupada; Neon recomienda conexión directa para migraciones o funciones de sesión. Consultar [conexión oficial de Neon](https://github.com/neondatabase/website/blob/main/content/docs/get-started/connect-neon.md).

Verificar schema/rol con una consulta mínima antes de aceptar trabajo. Limitar conexiones agregadas entre procesos, esperar pool dentro del deadline y liberar conexiones antes de LLM/HTTP. Registrar región/plan y capacidad de restore del entorno usado; la selección del proveedor no acredita su configuración.

### 3.3 Contrato, concurrencia y restore

Usar los mismos escenarios de contrato para SQLite y PostgreSQL. PostgreSQL necesita además dos conexiones/procesos compitiendo por evento y conversación, y un dueño vencido intentando finalizar. Verificar que solo el dueño vigente modifica el estado y que el commit parcial deja cero cambios.

El runner `scripts/e3/run_neon_h1.py` habilita sólo casos `@pytest.mark.neon` con flags explícitos, branch guard, rol, TLS y endpoint directo/pooled validados; `conftest.py` mantiene bloqueadas las demás pruebas. Migraciones/RLS/UoW y el núcleo de lease/fencing pasaron 6 checks. Ampliar esta campaña para ownership Telegram/outbox, `UNKNOWN_EFFECT`, import/restore y equivalencia completa de contratos.

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

Finalmente ejecutar evaluación real con `eval-e3` y límites definidos. Registrar E2E CLI/Telegram, G1–G9 y decisión de release según [VERIFICACION](VERIFICACION.md). Los scripts `scripts/e3/*` y `evals/run_e3.py` son entregables futuros: añadir comandos de uso exactos cuando existan.

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
