-- Apply only after exact-search baseline and HNSW evaluation are approved.
CREATE INDEX CONCURRENTLY IF NOT EXISTS knowledge_chunks_hnsw_idx
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
