-- Durable ownership for channel polling/dispatchers.
-- Unlike conversation claims this resource is global to a channel account: a
-- Telegram bot account may route messages to more than one tenant/deployment.
-- The transaction-local channel/account settings are the narrow RLS boundary.
CREATE TABLE IF NOT EXISTS dispatcher_claims (
    channel TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    generation BIGINT NOT NULL CHECK (generation > 0),
    lease_until TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (channel, account_ref)
);

CREATE INDEX IF NOT EXISTS dispatcher_claims_expiry_idx
    ON dispatcher_claims (lease_until);

ALTER TABLE dispatcher_claims ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dispatcher_claim_scope ON dispatcher_claims;
CREATE POLICY dispatcher_claim_scope ON dispatcher_claims
    USING (
        channel = NULLIF(current_setting('app.dispatch_channel', true), '')
        AND account_ref = NULLIF(current_setting('app.dispatch_account', true), '')
    )
    WITH CHECK (
        channel = NULLIF(current_setting('app.dispatch_channel', true), '')
        AND account_ref = NULLIF(current_setting('app.dispatch_account', true), '')
    );

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'd0_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON dispatcher_claims TO d0_runtime;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON dispatcher_claims TO incubia_runtime;
    END IF;
END
$$;
