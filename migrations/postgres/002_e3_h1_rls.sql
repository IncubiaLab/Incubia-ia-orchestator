-- E3-03: scope every Conversation data row and force application queries to
-- establish a transaction-local deployment/tenant context. Table ownership
-- remains with incubia_migrator; the runtime role is not an owner or bypass.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_runtime') THEN
        RAISE EXCEPTION 'E3-H1 runtime role incubia_runtime is missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_migrator') THEN
        RAISE EXCEPTION 'E3-H1 migration role incubia_migrator is missing';
    END IF;
END
$$;

ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS deployment_id TEXT;
ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS tenant_id TEXT;
UPDATE outcomes AS o
SET deployment_id = i.deployment_id, tenant_id = i.tenant_id
FROM inbox_events AS i
WHERE i.execution_id = o.execution_id
  AND (o.deployment_id IS NULL OR o.tenant_id IS NULL);
ALTER TABLE outcomes ALTER COLUMN deployment_id SET NOT NULL;
ALTER TABLE outcomes ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS deployment_id TEXT;
ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS tenant_id TEXT;
UPDATE deliveries AS d
SET deployment_id = i.deployment_id, tenant_id = i.tenant_id
FROM inbox_events AS i
WHERE i.execution_id = d.execution_id
  AND (d.deployment_id IS NULL OR d.tenant_id IS NULL);
ALTER TABLE deliveries ALTER COLUMN deployment_id SET NOT NULL;
ALTER TABLE deliveries ALTER COLUMN tenant_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'inbox_scope_execution_uq') THEN
        ALTER TABLE inbox_events ADD CONSTRAINT inbox_scope_execution_uq
            UNIQUE (deployment_id, tenant_id, execution_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'turns_scope_inbox_fk') THEN
        ALTER TABLE turns ADD CONSTRAINT turns_scope_inbox_fk
            FOREIGN KEY (deployment_id, tenant_id, execution_id)
            REFERENCES inbox_events (deployment_id, tenant_id, execution_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'turns_conversation_scope_fk') THEN
        ALTER TABLE turns ADD CONSTRAINT turns_conversation_scope_fk
            FOREIGN KEY (deployment_id, tenant_id, conversation_id, actor_id)
            REFERENCES conversations (deployment_id, tenant_id, conversation_id, actor_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'outcomes_scope_inbox_fk') THEN
        ALTER TABLE outcomes ADD CONSTRAINT outcomes_scope_inbox_fk
            FOREIGN KEY (deployment_id, tenant_id, execution_id)
            REFERENCES inbox_events (deployment_id, tenant_id, execution_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'deliveries_scope_inbox_fk') THEN
        ALTER TABLE deliveries ADD CONSTRAINT deliveries_scope_inbox_fk
            FOREIGN KEY (deployment_id, tenant_id, execution_id)
            REFERENCES inbox_events (deployment_id, tenant_id, execution_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS inbox_scope_state_idx
    ON inbox_events (deployment_id, tenant_id, state, received_at);
CREATE INDEX IF NOT EXISTS turns_conversation_history_idx
    ON turns (deployment_id, tenant_id, conversation_id, actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS deliveries_scope_state_idx
    ON deliveries (deployment_id, tenant_id, state, created_at);

ALTER TABLE inbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE deliveries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS inbox_tenant_scope ON inbox_events;
CREATE POLICY inbox_tenant_scope ON inbox_events
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS conversations_tenant_scope ON conversations;
CREATE POLICY conversations_tenant_scope ON conversations
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS turns_tenant_scope ON turns;
CREATE POLICY turns_tenant_scope ON turns
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS outcomes_tenant_scope ON outcomes;
CREATE POLICY outcomes_tenant_scope ON outcomes
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS deliveries_tenant_scope ON deliveries;
CREATE POLICY deliveries_tenant_scope ON deliveries
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO incubia_runtime;
REVOKE CREATE ON SCHEMA public FROM incubia_runtime;
GRANT SELECT ON schema_migrations TO incubia_runtime;
GRANT SELECT, INSERT, UPDATE ON inbox_events, conversations TO incubia_runtime;
GRANT SELECT, INSERT ON turns, outcomes, deliveries TO incubia_runtime;
