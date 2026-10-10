-- Shared leases and fencing tokens. A resource keeps its generation after
-- release/expiry so a later owner can never reuse a stale token.
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

GRANT SELECT, INSERT, UPDATE ON resource_claims TO incubia_runtime;
