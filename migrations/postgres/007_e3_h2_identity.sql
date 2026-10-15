-- H2 identity state.  Memberships are tenant scoped; bindings are resolved
-- through a trusted channel/account boundary before a tenant scope exists.
CREATE TABLE IF NOT EXISTS memberships (
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('actor', 'operator', 'admin')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (deployment_id, tenant_id, subject_id)
);

CREATE INDEX IF NOT EXISTS memberships_subject_idx
    ON memberships (deployment_id, subject_id, active);

CREATE TABLE IF NOT EXISTS bindings (
    channel TEXT NOT NULL,
    channel_account_ref TEXT NOT NULL,
    external_chat_ref TEXT NOT NULL,
    external_sender_ref TEXT NOT NULL,
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (channel, channel_account_ref, external_chat_ref, external_sender_ref),
    FOREIGN KEY (deployment_id, tenant_id, actor_id)
        REFERENCES memberships (deployment_id, tenant_id, subject_id)
);

CREATE INDEX IF NOT EXISTS bindings_scope_idx
    ON bindings (deployment_id, tenant_id, actor_id, enabled);

ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS memberships_tenant_scope ON memberships;
CREATE POLICY memberships_tenant_scope ON memberships
    USING (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        deployment_id = NULLIF(current_setting('app.deployment_id', true), '')
        AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
    );

ALTER TABLE bindings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bindings_channel_scope ON bindings;
CREATE POLICY bindings_channel_scope ON bindings
    USING (
        channel = NULLIF(current_setting('app.binding_channel', true), '')
        AND channel_account_ref = NULLIF(current_setting('app.binding_account', true), '')
    )
    WITH CHECK (
        channel = NULLIF(current_setting('app.binding_channel', true), '')
        AND channel_account_ref = NULLIF(current_setting('app.binding_account', true), '')
    );

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_runtime') THEN
        GRANT SELECT ON memberships, bindings TO incubia_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'd0_runtime') THEN
        REVOKE ALL ON memberships, bindings FROM d0_runtime;
    END IF;
END
$$;
