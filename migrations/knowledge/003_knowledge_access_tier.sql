-- Forward-only expand migration for 3-layer Knowledge access tiers.
-- Existing rows default fail-closed to 'admin_only'.
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS access_tier TEXT NOT NULL DEFAULT 'admin_only'
    CHECK (access_tier IN ('workspace_general', 'admin_only'));

CREATE INDEX IF NOT EXISTS knowledge_sources_access_tier_idx
    ON knowledge_sources (access_tier)
    WHERE revoked_at IS NULL;

