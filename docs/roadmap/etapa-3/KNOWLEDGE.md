# Knowledge — etapa 3

Retrieval, embeddings e ingestión pertenecen a Knowledge. [ADR-010](../../adr/ADR-ORCH-010-RAG-VECTOR-STORE.md) acepta Neon/PostgreSQL con pgvector como backend canónico y una base por deployment. El Data Plane de Knowledge no usa filas multi-tenant para aislar clientes: el Control Plane resuelve el `deployment_id` confiable y selecciona base, credenciales y pool antes de retrieval.

## Incremento propuesto

Ingestar documentos de texto sintéticos de dos deployments mediante comando administrativo autorizado. Cada base contiene fuentes, versiones, chunks, embeddings y generaciones de índice. Una generación progresa `BUILDING → VALIDATING → ACTIVE → RETIRED` o `FAILED`; sólo una generación validada se publica mediante swap atómico. Chunks referencian fuente, versión, chunk y generación; un reindex no mezcla modelos/dimensiones. Revocación excluye la fuente de nuevas consultas inmediatamente; purga física/backups sigue retención.

RetrievalPort inicia con fake determinista para probar contratos. E3-10 implementa pgvector y compara búsqueda exacta por similitud coseno con HNSW mediante feature flag; no compara ni incorpora un store externo. Fijar modelo de embeddings, dimensión y versión antes de indexar; reservar presupuesto antes de llamadas remotas. Filtros internos complejos usan búsqueda exacta o fallback mientras no exista evidencia de que HNSW preserva recall.

## Dataset y límites

≥60 consultas: ≥20 dev y ≥40 val, con IDs de fuentes/chunks/generaciones relevantes esperados, casos no respondibles y deployment. Val contiene al menos 10 casos sin respuesta y 10 intentos cross-deployment; las métricas de recall se calculan solo sobre casos respondibles. Hash y split congelados en informe.

Top_k máximo 5, tamaño y tokens de evidencia acotados por ContextBuilder. Una búsqueda vacía no genera hechos; seleccionar abstención o fallback. Fuentes tienen referencias que el actor puede abrir o descripciones públicas seguras. G5/G6 especifican umbrales.

## Riesgos a probar

Injection documental, routing o credenciales cross-deployment, pool/caché compartido, fuentes revocadas, generación parcial, dimensión incompatible, embedding fallido y borrado/reindex concurrente. Cachés incluyen `deployment_id`, generación y versión de policy; no reutilizar resultados de otro deployment.
