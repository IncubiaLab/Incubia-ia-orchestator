# Knowledge — etapa 3

Retrieval, embeddings e ingestión pertenecen a Knowledge. [ADR-010](../../adr/ADR-ORCH-010-RAG-VECTOR-STORE.md) acepta Neon/PostgreSQL con pgvector como backend canónico y una base por deployment. El Data Plane de Knowledge no usa filas multi-tenant para aislar clientes: el Control Plane resuelve el `deployment_id` confiable y selecciona base, credenciales y pool antes de retrieval.

## Slice implementado y salida pendiente

Al 2026-10-15 existen contratos y fake scoped, dataset `evals/e3` con 100 consultas (20 dev, 80 val) y 24 escenarios, manifest SHA-256, migraciones separadas en `migrations/knowledge/`, adapter PostgreSQL de búsqueda exacta e ingestión por generaciones, y respuesta extractiva opcional. La campaña Neon sintética en dos bases ejecutó pgvector con `text-embedding-3-small` a 384 dimensiones dentro del presupuesto aprobado. Ese intento OpenAI falló G5; la repetición con modelo local versionado pasó recall, abstención y latencia. `HashEmbedding` queda sólo para ensayos offline; exact/HNSW, revocación y rollback se evaluaron. G6 técnico pasó, pero falta firma manual y READ real integrado. E3-4 sigue abierto.

## Incremento propuesto

Ingestar documentos de texto sintéticos de dos deployments mediante comando administrativo autorizado. Cada base contiene fuentes, versiones, chunks, embeddings y generaciones de índice. Una generación progresa `BUILDING → VALIDATING → ACTIVE → RETIRED` o `FAILED`; sólo una generación validada se publica mediante swap atómico. Chunks referencian fuente, versión, chunk y generación; un reindex no mezcla modelos/dimensiones. Revocación excluye la fuente de nuevas consultas inmediatamente; purga física/backups sigue retención.

RetrievalPort ya tiene fake determinista. E3-10 tiene adapter exacto y esquema pgvector sin campaña real; debe comparar búsqueda exacta por similitud coseno con HNSW mediante feature flag; no compara ni incorpora un store externo. Fijar modelo de embeddings, dimensión y versión antes de indexar; reservar presupuesto antes de llamadas remotas. Filtros internos complejos usan búsqueda exacta o fallback mientras no exista evidencia de que HNSW preserva recall.

## Dataset y límites

≥60 consultas: ≥20 dev y ≥40 val, con IDs de fuentes/chunks/generaciones relevantes esperados, casos no respondibles y deployment. Val contiene al menos 10 casos sin respuesta y 10 intentos cross-deployment; las métricas de recall se calculan solo sobre casos respondibles. Hash y split congelados en informe.

Top_k máximo 5, tamaño y tokens de evidencia acotados por ContextBuilder. Una búsqueda vacía no genera hechos; seleccionar abstención o fallback. Fuentes tienen referencias que el actor puede abrir o descripciones públicas seguras. G5/G6 especifican umbrales.

## Riesgos a probar

Injection documental, routing o credenciales cross-deployment, pool/caché compartido, fuentes revocadas, generación parcial, dimensión incompatible, embedding fallido y borrado/reindex concurrente. Cachés incluyen `deployment_id`, generación y versión de policy; no reutilizar resultados de otro deployment.


Actualización E3-4 (2026-10-15): [G5 local en Neon](../../../evals/results/e3-4-neon-local-2026-10-15.json) pasó 40/40 recall, 40/40 abstención, p95 0,6177 s, cero fugas, exact/HNSW y pruebas de revocación/rollback. [G6 técnico](../../../evals/results/e3-4-g6-neon-local-2026-10-15.json) evaluó 24 casos: 12/12 afirmaciones respaldadas, 6/6 referencias del manifiesto y cero fallos críticos; la URL pública READ respondió 200 anónimo. El gate sigue abierto por rúbrica manual sin firma y READ de G6 ejecutada con fixture HTTP. El resultado OpenAI anterior fallido se conserva como historial; el modelo local versionado es el candidato actual.
