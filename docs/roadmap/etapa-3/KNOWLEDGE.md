# Knowledge — etapa 3

Retrieval, embeddings e ingestión pertenecen a Knowledge. [ADR Neon](../../adr/ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md) selecciona persistencia relacional; la elección vectorial sigue ADR-010 y no queda decidida por este plan.

## Incremento propuesto

Ingestar documentos de texto sintéticos de dos tenants mediante comando administrativo autorizado. Source contiene tenant/deployment, versión, hash, origen y lifecycle ACTIVE/REVOKED. Chunks referencian versión; un reindex no mezcla vectores entre modelos/dimensiones. Mantener un índice activo por versión y cambiarlo atómicamente tras completar ingestión. Revocación excluye la fuente de nuevas consultas inmediatamente; purga física/backups sigue retención.

RetrievalPort inicia con fake determinista para probar contratos. Evaluar PostgreSQL/pgvector frente a store separado usando recall, latencia, aislamiento, borrado y costo. En E3-10 registrar decisión y adapter seleccionado; no construir ambos. Fijar modelo de embeddings, dimensión y versión antes de indexar; reservar presupuesto antes de llamadas remotas.

## Dataset y límites

≥60 consultas: ≥20 dev y ≥40 val, con IDs de fuentes/chunks relevantes esperados, casos no respondibles y tenant. Val contiene al menos 10 casos sin respuesta y 10 intentos cross-tenant; las métricas de recall se calculan solo sobre casos respondibles. Hash y split congelados en informe.

Top_k máximo 5, tamaño y tokens de evidencia acotados por ContextBuilder. Una búsqueda vacía no genera hechos; seleccionar abstención o fallback. Fuentes tienen referencias que el actor puede abrir o descripciones públicas seguras. G5/G6 especifican umbrales.

## Riesgos a probar

Injection documental, filtros tenant omitidos, caché compartida, fuentes revocadas, índice parcial, dimensión incompatible, embedding fallido y borrado/reindex concurrente. Cachés incluyen scope y source/model version; no reutilizar resultados de otro tenant.
