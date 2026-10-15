-- E3-D0 local compatibility for the claim-aware runtime.
--
-- The local baseline keeps the same claim contract as H1 without requiring
-- the complete Neon/RLS migration chain (which also provisions the H1 roles
-- and dispatcher/restore objects).  This migration is intentionally scoped
-- to the synthetic d0_runtime role and is harmless when an H1 database has
-- already created resource_claims through 003_e3_h1_claims.sql.
-- The claim-aware ledger also writes the tenant scope on outcomes and
-- deliveries.  The original D0 tables predate that H1-compatible shape, so
-- add the columns here for a fresh local Compose database.
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS deployment_id TEXT;
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS deployment_id TEXT;
ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS tenant_id TEXT;

UPDATE outcomes AS o
SET deployment_id = i.deployment_id, tenant_id = i.tenant_id
FROM inbox_events AS i
WHERE i.execution_id = o.execution_id
  AND (o.deployment_id IS NULL OR o.tenant_id IS NULL);
UPDATE deliveries AS d
SET deployment_id = i.deployment_id, tenant_id = i.tenant_id
FROM inbox_events AS i
WHERE i.execution_id = d.execution_id
  AND (d.deployment_id IS NULL OR d.tenant_id IS NULL);

ALTER TABLE outcomes ALTER COLUMN deployment_id SET NOT NULL;
ALTER TABLE outcomes ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE deliveries ALTER COLUMN deployment_id SET NOT NULL;
ALTER TABLE deliveries ALTER COLUMN tenant_id SET NOT NULL;

CREATE TABLE IF NOT EXISTS resource_claims (
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    generation BIGINT NOT NULL CHECK (generation > 0),
    lease_until TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (deployment_id, tenant_id, resource_type, resource_key)
);

CREATE INDEX IF NOT EXISTS resource_claims_expiry_idx
    ON resource_claims (deployment_id, tenant_id, lease_until);

ALTER TABLE resource_claims ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS resource_claims_tenant_scope ON resource_claims;
CREATE POLICY resource_claims_tenant_scope ON resource_claims
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'd0_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON resource_claims TO d0_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON resource_claims TO incubia_runtime;
    END IF;
END
$$;
