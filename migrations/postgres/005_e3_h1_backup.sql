-- E3-05 import audit.  Backup payloads stay outside PostgreSQL; this table
-- records only the sanitized manifest and the outcome of each restore.
CREATE TABLE IF NOT EXISTS ledger_imports (
    import_id TEXT PRIMARY KEY,
    manifest_hash TEXT NOT NULL UNIQUE,
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    manifest_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    table_counts JSONB NOT NULL,
    revision_min BIGINT,
    revision_max BIGINT,
    reconciled_unknown_effects INTEGER NOT NULL DEFAULT 0,
    cleared_claims INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    rpo_seconds DOUBLE PRECISION,
    rto_seconds DOUBLE PRECISION,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS ledger_imports_scope_idx
    ON ledger_imports (deployment_id, tenant_id, created_at DESC);

-- Imports run with the direct migration role.  Runtime must not be able to
-- forge or alter restore evidence.
REVOKE ALL ON ledger_imports FROM PUBLIC;
REVOKE ALL ON ledger_imports FROM incubia_runtime;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'incubia_migrator') THEN
        GRANT SELECT, INSERT, UPDATE ON ledger_imports TO incubia_migrator;
    END IF;
END
$$;
