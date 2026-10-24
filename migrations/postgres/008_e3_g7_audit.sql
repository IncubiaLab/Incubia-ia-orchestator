-- E3-5 / G7: durable, tenant-scoped, append-only audit log.
-- Additive only (expand step): older app images ignore this table.
-- The runtime role gets INSERT and SELECT only; no UPDATE/DELETE grant, and
-- RLS pins every row to the session deployment/tenant.
-- Stores identifiers, a resource hash and bounded classifications; never
-- tool inputs, credentials or resource names.
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    tool_call_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    resource_sha256 TEXT NOT NULL,
    decision TEXT,
    attempt INTEGER CHECK (attempt IS NULL OR attempt > 0),
    status TEXT,
    error_code TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS audit_events_execution_idx
    ON audit_events (deployment_id, tenant_id, execution_id, occurred_at);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_events_tenant_scope ON audit_events;
CREATE POLICY audit_events_tenant_scope ON audit_events
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
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_runtime') THEN
        REVOKE ALL ON audit_events FROM incubia_runtime;
        GRANT SELECT, INSERT ON audit_events TO incubia_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'd0_runtime') THEN
        REVOKE ALL ON audit_events FROM d0_runtime;
    END IF;
END
$$;
