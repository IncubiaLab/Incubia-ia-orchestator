CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inbox_events (
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    channel_account_ref TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    request_id UUID NOT NULL,
    execution_id UUID NOT NULL UNIQUE,
    state TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminal_at TIMESTAMPTZ,
    PRIMARY KEY (deployment_id, tenant_id, channel, channel_account_ref, external_event_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (deployment_id, tenant_id, conversation_id, actor_id)
);

CREATE TABLE IF NOT EXISTS turns (
    execution_id UUID PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outcomes (
    execution_id UUID PRIMARY KEY,
    outcome_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deliveries (
    execution_id UUID NOT NULL,
    response_id TEXT NOT NULL,
    destination_ref TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (execution_id, response_id, destination_ref)
);

-- E3-D0 uses d0_runtime; the Neon H1 branch uses incubia_runtime. In either
-- case the migration must fail closed if no runtime role was provisioned.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('d0_runtime', 'incubia_runtime')) THEN
        RAISE EXCEPTION 'No approved runtime role is provisioned';
    END IF;
END
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'd0_runtime') THEN
        GRANT USAGE ON SCHEMA public TO d0_runtime;
        REVOKE CREATE ON SCHEMA public FROM d0_runtime;
        GRANT SELECT ON schema_migrations TO d0_runtime;
        GRANT SELECT, INSERT, UPDATE ON inbox_events, conversations TO d0_runtime;
        GRANT SELECT, INSERT ON turns, outcomes, deliveries TO d0_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_runtime') THEN
        GRANT USAGE ON SCHEMA public TO incubia_runtime;
        REVOKE CREATE ON SCHEMA public FROM incubia_runtime;
        GRANT SELECT ON schema_migrations TO incubia_runtime;
        GRANT SELECT, INSERT, UPDATE ON inbox_events, conversations TO incubia_runtime;
        GRANT SELECT, INSERT ON turns, outcomes, deliveries TO incubia_runtime;
    END IF;
END
$$;
