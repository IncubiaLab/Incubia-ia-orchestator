-- Run separately in each deployment Data Plane. Requires pgvector privileges.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS knowledge_generations (
    generation_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('BUILDING','VALIDATING','ACTIVE','RETIRED','FAILED')),
    model_version TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK (dimension = 384),
    corpus_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_one_active_generation
    ON knowledge_generations ((status)) WHERE status = 'ACTIVE';
CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    public_ref TEXT,
    revoked_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    generation_id TEXT NOT NULL REFERENCES knowledge_generations(generation_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
    source_version TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    PRIMARY KEY (generation_id, chunk_id)
);
CREATE INDEX IF NOT EXISTS knowledge_chunks_exact_idx
    ON knowledge_chunks (generation_id, source_id);
-- Optional, activated only after exact-search recall and latency evaluation.
-- CREATE INDEX knowledge_chunks_hnsw_idx ON knowledge_chunks
-- USING hnsw (embedding vector_cosine_ops);
