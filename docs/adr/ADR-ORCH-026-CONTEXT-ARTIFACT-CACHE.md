# ADR-ORCH-026 — Jerarquía de caché de artefactos de contexto

**Status:** Proposed — 2026-10-08  
**Fecha:** 2026-10-08  
**Scope:** Conversation, Knowledge, Orchestration y adapters de caché  
**Fuente de seguimiento:** propuesta local pendiente de ratificación en el registro de ADRs

## Contexto

El `ContextBuilder` ya impone límites de tokens, historial y hechos, pero su
estrategia actual parte de cargar un snapshot y recortar contexto por posición.
No puede tratar de forma eficiente una conversación extensa, memoria resumida,
evidencia de Knowledge y resultados de tools al mismo tiempo.

La caché necesaria no debe ser una segunda fuente de verdad ni una forma de
evitar las comprobaciones de identidad o policy. Debe conservar artefactos
derivados, acelerar lecturas y ayudar a construir un *working set* pequeño que
quepa en el presupuesto del perfil.

Las fronteras existentes condicionan esta decisión:

- Conversation es la autoridad canónica para turnos, hechos versionados,
  revisión y resultados lógicos (ADR-ORCH-008).
- Knowledge usa Neon/PostgreSQL + pgvector, una base por deployment, y publica
  generaciones de índice completas (ADR-ORCH-010).
- `GraphState` es privado del adapter de LangGraph y no es memoria durable de
  producto (ADR-ORCH-019).
- Identity/Tenant y Policy deben poder revocar acceso mientras exista una
  entrada aparentemente válida.

## Decisión

Incubia adopta una **jerarquía de caché de artefactos de contexto**. La caché
será derivada, versionada, descartable y *scope-aware*. Ninguna entrada de
caché concede autorización ni sustituye una lectura canónica cuando la
corrección o la seguridad la requieren.

### Jerarquía

```text
L0  memoización de la ejecución actual
 ↓
L1  caché caliente acotada por proceso
 ↓
L2  caché derivada compartida, detrás de un adapter
 ↓
Conversation / Knowledge / Tool adapters canónicos
```

#### L0 — Memoización de ejecución

Vive únicamente durante un `request_id`/`execution_id`. Evita repetir dentro
del mismo workflow una lectura de snapshot, retrieval o tool READ idéntica.
No requiere invalidación remota y se destruye al terminar la ejecución.

#### L1 — Caché caliente local

Es una caché en memoria del proceso, con límite de bytes, TTL y eviction LRU o
TinyLFU. Reduce latencia en instalaciones locales y funciona sin añadir una
dependencia al modo offline. No se asume coherencia entre procesos; una
entrada sólo puede servirse si sus versiones y su scope siguen siendo válidos.

#### L2 — Caché compartida

Es una caché derivada compartida para múltiples workers, inicialmente
compatible con Redis/Valkey mediante un adapter intercambiable. La elección o
provisión del backend no forma parte de este ADR. El contrato debe permitir
operar sin L2 y degradar a los stores canónicos.

L2 no será un ledger, una base de Knowledge ni un mecanismo de claims. No se
usará para prometer atomicidad con el commit de Conversation o con una entrega
externa.

### Artefactos cacheables

Los puertos deben pertenecer al contexto que conoce la semántica del artefacto;
no se crea un puerto genérico en `orchestration` que permita saltarse esas
fronteras.

1. **Snapshot de Conversation.** Se puede cachear por revisión exacta. La
   revisión canónica sigue siendo la autoridad y la entrada se descarta si el
   snapshot solicitado ya no coincide.
2. **Resumen episódico.** Resume un intervalo de revisiones y declara qué
   revisiones cubre. Es una materialización derivada; los hechos canónicos y
   los turnos recientes tienen prioridad si existe conflicto.
3. **Resultados de Retrieval.** Se cachean sólo con generación de Knowledge,
   estado de revocación y contexto de policy compatibles.
4. **Resultados de tools READ.** Se cachean sólo cuando la semántica del
   recurso permite frescura acotada y la policy autoriza la lectura actual.
5. **Context pack.** Puede cachearse como resultado de la selección y
   serialización de candidatos, nunca como permiso. Antes de servirlo se
   validan sus dependencias y se excluyen artefactos vencidos.

La respuesta final del LLM no se cacheará en el primer corte. Una caché
semántica de respuestas sólo podrá evaluarse más adelante para contenido
público, sin estado de conversación, sin tools y sin mutaciones.

### Scope y clave de caché

Cada entrada incluye un envelope con la versión del contrato, dependencias,
frescura y clasificación de datos. Las dimensiones obligatorias son:

```text
artifact_type
deployment_id
tenant_id                 # cuando el artefacto no sea público del deployment
conversation_id           # para memoria conversacional
actor_id                  # para memoria privada o permisos por actor
policy_version
principal_fingerprint     # roles, membresías y ACL relevantes
context_schema_version
```

Además, según el artefacto, se incluyen:

```text
conversation_revision
knowledge_generation
source_epoch
profile_id / profile_version
tool_snapshot_version
normalized_query_hash
filters / top_k / token_limit
model / instruction_version
```

El `principal_fingerprint` no contiene credenciales. Representa de forma
estable la autorización efectiva necesaria para detectar cambios de roles,
membresías o ACL. Un cambio de autorización no espera a que expire el TTL.

No se aceptan `deployment_id`, DSNs, nombres de base, credenciales ni
identidad efectiva desde el usuario, el prompt o el LLM para construir claves.
El scope confiable se resuelve antes de consultar la caché.

### Frescura e invalidación

El sistema valida dependencias versionadas antes de devolver una entrada:

- `conversation_revision` para memoria y snapshots;
- `knowledge_generation` para embeddings y retrieval;
- `source_epoch` para revocación de documentos;
- `policy_version` y `principal_fingerprint` para autorización;
- `profile_version`, `tool_snapshot_version` y `context_schema_version` para
  materializaciones de contexto;
- modelo e instrucciones para cualquier artefacto dependiente del LLM.

La invalidación preferida es lógica y monotónica: publicar una nueva revisión,
generación o epoch hace inválidas las entradas anteriores sin requerir un scan
global. La revocación de una fuente o permiso invalida inmediatamente las
lecturas afectadas.

`stale-while-revalidate` sólo se permite para artefactos de bajo riesgo, con
dependencias de autorización aún vigentes. No se puede servir stale después de
una revocación, un cambio de policy o un cambio de deployment.

### Construcción del contexto

El flujo usará *cache-aside*:

1. Resolver el scope confiable y consultar la revisión/policy vigente.
2. Leer candidatos desde L0, L1 y L2, validando sus envelopes.
3. Recuperar de las fuentes canónicas los misses o artefactos inválidos.
4. Deduplicar, priorizar y aplicar el presupuesto de contexto.
5. Construir el `context pack` con este orden mínimo:

   ```text
   instrucciones obligatorias
   restricciones y policy aplicables
   hechos críticos
   evidencia relevante
   resumen episódico
   turnos recientes
   mensaje actual
   ```

6. Reservar espacio para la respuesta y rechazar de forma segura si lo
   obligatorio no cabe.

Los hechos, documentos y resultados de tools siguen siendo datos no confiables;
la caché no los convierte en instrucciones ni les permite cambiar routing,
policy, permisos o tools.

### Concurrencia y fallos

El adapter debe soportar *single-flight* por clave para evitar el *cache
stampede*. Si varios workers solicitan el mismo artefacto, sólo uno lo
materializa y los demás esperan un resultado acotado o consultan el origen.

La caída, timeout o corrupción de L1/L2 degrada latencia, pero no cambia la
semántica: se consulta la fuente canónica o se devuelve un error seguro. La
caché no participa en el `ConversationUnitOfWork`, claims, fencing, inbox,
outbox ni commits de entrega.

### Retención y observabilidad

Los TTL iniciales son parámetros de despliegue y deben validarse con carga:

- instrucciones/perfiles: preferentemente invalidación por versión;
- snapshots: TTL corto y revisión exacta;
- resúmenes: reutilización por intervalo de revisiones;
- retrieval: TTL corto condicionado por generación y `source_epoch`;
- tools READ: TTL definido por la semántica del recurso;
- respuestas finales: deshabilitadas.

Se emiten métricas sanitizadas de `hit`, `miss`, edad, bytes, tokens evitados,
costo estimado evitado, motivo de invalidación, esperas de single-flight y
errores. No se registran prompts, documentos, respuestas, claves ni
credenciales por defecto.

## Ownership y puertos

Los contratos previstos son:

- `ConversationSnapshotCachePort` para snapshots y resúmenes de Conversation;
- `RetrievalCachePort` para resultados de Knowledge;
- un puerto de materialización de contexto en Orchestration sólo si su
  frontera es necesaria y no duplica los puertos anteriores;
- adapters mecánicos L1/L2 que no contienen decisiones de dominio.

La composición selecciona adapters. Domain/Application no importan Redis,
drivers, SDKs ni tipos específicos del proveedor.

## Consecuencias

### Beneficios

- El contexto permanece limitado aunque la conversación y Knowledge crezcan.
- Se reduce latencia, tokens repetidos y costo de retrieval/embeddings/tools.
- La invalidación por versión es más segura que una política basada sólo en
  TTL.
- L1 mantiene el modo offline; L2 permite escalar a varios workers.
- Conversation, Knowledge, Identity y Policy conservan ownership claro.

### Costes y riesgos

- Se introducen contratos, envelopes, métricas y pruebas de invalidación.
- Los artefactos resumidos pueden contener errores y deben reconciliarse con la
  fuente canónica.
- L2 añade una dependencia operativa si se activa.
- Un hit de caché no demuestra autorización: cada adapter debe respetar el
  scope y las versiones actuales.

## Alternativas descartadas

### Guardar todo en GraphState

Se descarta porque GraphState pertenece al runtime y no puede ser memoria de
producto ni sobrevivir de forma independiente a LangGraph.

### Usar sólo un TTL global

Se descarta porque no detecta revocaciones, cambios de policy, nuevas
generaciones de Knowledge ni revisiones de conversación.

### Cachear siempre el prompt o la respuesta final

Se descarta en el primer corte porque puede devolver información personalizada
u obsoleta y ocultar cambios de autorización, estado o herramientas.

### Hacer de Redis/Valkey la fuente canónica

Se descarta porque rompe los contratos de persistencia, recuperación,
idempotencia y restore establecidos para Conversation y Knowledge.

### Un puerto genérico de caché usado por todos los contextos

Se descarta porque permite que Orchestration o un adapter reutilice datos sin
conocer ownership, ACL, generación o política del contexto que los produjo.

## Plan incremental

1. Versionar envelopes y puertos de cacheo junto con los contratos de
   Conversation y Knowledge.
2. Implementar L0 y L1 con métricas y límites, conservando el modo offline.
3. Integrar `ContextPlanner`/`ContextBuilder` con candidatos priorizados,
   resúmenes y presupuesto duro.
4. Añadir cacheo de retrieval condicionado por generation, source epoch y
   policy; probar revocación y casos cross-deployment.
5. Añadir single-flight y un adapter L2 sólo después de medir que múltiples
   workers lo necesitan.
6. Evaluar resúmenes episódicos y, separadamente, cualquier caché semántica de
   contenido público.

## Criterios de validación

- Cero lecturas cross-deployment, cross-tenant o cross-actor en todas las
  capas.
- Una revocación de documento o permiso no sirve una entrada anterior.
- Una nueva revisión de Conversation no sirve un snapshot incoherente.
- Una nueva generación pgvector no reutiliza resultados de la anterior.
- L1/L2 caídos no causan pérdida, duplicación lógica ni commit parcial.
- El `context pack` respeta `max_input_tokens` y conserva instrucciones y
  restricciones obligatorias.
- Retrieval mantiene el objetivo de p95 ≤1 s bajo el perfil MVP y el flujo
  completo conserva el objetivo provisional de p95 ≤5 s bajo carga acordada.
- Las métricas no contienen prompts, respuestas, documentos, secretos ni
  credenciales.
- La suite offline funciona sin L2 y los tests de contrato validan adapters
  intercambiables.

## Relacionado

- ADR-ORCH-008 — Persistencia de Conversation State
- ADR-ORCH-010 — Arquitectura RAG y Vector Store
- ADR-ORCH-019 — Separación entre Conversation State y GraphState
- ADR-ORCH-025 — PostgreSQL administrado con Neon para Tier 3
- Spec 07 — Contextos y capacidades posteriores
- E3-09, E3-10, E3-11, E3-12 y E3-13
