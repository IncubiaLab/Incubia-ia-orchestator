#!/usr/bin/env sh
# The official PostgreSQL entrypoint runs this only while initializing an empty
# local volume.  Values stay in Compose environment, never in the image.
set -eu

: "${D0_RUNTIME_PASSWORD:?D0_RUNTIME_PASSWORD is required}"

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 --set=runtime_password="$D0_RUNTIME_PASSWORD" >/dev/null <<'EOSQL'
SELECT format('CREATE ROLE d0_runtime LOGIN PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'd0_runtime')
\gexec
EOSQL
