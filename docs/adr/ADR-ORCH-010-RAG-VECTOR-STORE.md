# ADR-ORCH-010 — Arquitectura RAG y Vector Store

**Estado:** Accepted  
**Fecha:** 2026-10-07  
**Alcance:** Knowledge, RAG y persistencia vectorial del MVP.  
**Fuente de seguimiento:** [HEC-35](https://linear.app/hector-cruz/issue/HEC-35/adr-orch-010-arquitectura-rag-y-vector-store) · [documento en Linear](https://linear.app/hector-cruz/document/adr-orch-010-arquitectura-rag-y-vector-store-05b9122b8809)

## Decisión

Incubia adopta **Neon/PostgreSQL con pgvector** como backend canónico de
conocimiento y retrieval del MVP.

La frontera de aislamiento es **database-per-deployment**:

```text
un deployment / organización → una base Neon → un esquema Knowledge + pgvector
```

No habrá multi-tenancy por filas en el Data Plane de Knowledge. La resolución
confiable de `deployment_id` selecciona la base, credenciales y pool correctos
antes de ejecutar retrieval. `deployment_id` permanece en el Control Plane,
trazas y auditoría; no se usa como predicado de aislamiento entre clientes
dentro de las tablas RAG.

Knowledge posee `EmbeddingPort`, `KnowledgeRepository` y `RetrievalPort`.
Orchestration consume `EvidenceItem`; no consulta SQL, pgvector ni SDKs
directamente.

## Modelo y publicación

Cada base de deployment mantiene fuentes, versiones, chunks, embeddings y
generaciones de índice. Una generación pasa por:

```text
BUILDING → VALIDATING → ACTIVE → RETIRED
                 ↘ FAILED
```

Una ingestión es idempotente por fuente, hash, versión de chunker y modelo de
embeddings. Sólo una generación validada se publica mediante swap atómico; una
generación parcial nunca queda visible. Las fuentes revocadas se excluyen de
inmediato de nuevas consultas y se purgan según retención.

Cada generación activa usa un único modelo y dimensión de embedding. Cambiar
modelo o dimensión crea una generación nueva; no se mezclan vectores
incompatibles.

## Retrieval y seguridad

`RetrievalPort` recibe un scope confiable de ejecución, consulta, `top_k`,
deadline, capability y políticas internas de acceso. La base ya representa al
deployment; los permisos por documento, rol o departamento se resuelven como
ACL/RLS interno cuando apliquen, no como aislamiento entre clientes.

Los documentos, resultados de tools y evidencia recuperada son datos no
confiables: no cambian policy, permisos, tools ni instrucciones de sistema.
`EvidenceItem` conserva fuente, versión, chunk, generación y score opcional
para construir el manifest de ADR-009.

No se aceptan nombres de base, DSNs ni credenciales desde usuarios, LLMs o
prompts. El Control Plane mantiene un `deployment_registry` con referencias
seguras a conexión; cada deployment usa credenciales y pool separados. Caches
futuros deben incluir `deployment_id`, generation y policy version.

## Índices y evaluación

La búsqueda exacta por similitud coseno es el baseline de calidad. HNSW es la
primera optimización permitida y se activa por feature flag sólo tras evidencia.
Los filtros internos complejos pueden usar búsqueda exacta o fallback para
proteger recall.

E3-10 ya no compara pgvector con un vector store externo. Evalúa
configuraciones exactas y HNSW de pgvector con el mismo corpus, modelo,
dimensión, concurrencia y presupuesto.

Criterios mínimos: recall@5 >= 85 % en casos respondibles; abstención >= 90 %
en no respondibles; cero routing, credenciales, pools o cachés
cross-deployment; cero uso de fuentes revocadas; cero generación parcial;
reingesta idempotente; rollback/reindexado reproducibles; y p95 de retrieval
<= 1 s bajo el perfil MVP.

## Consecuencias

Se simplifica la operación del MVP al mantener metadatos, documentos/chunks y
vectores en Neon. A cambio, se requiere provisioning, migraciones,
observabilidad y gestión de pools por deployment.

Esta aceptación fija el backend y la topología. E3-10 queda como evidencia
operativa para configurar índices y parámetros; no reabre la selección de
vector store.
