#!/usr/bin/env bash
# Reproducible local evidence for E3-D0-L. It creates an isolated Compose
# project and removes only its own named volume on exit.
set -euo pipefail

task_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
task_project="incubia-e3-d0-smoke-$$"
preflight_id=""
export D0_MIGRATOR_PASSWORD="${D0_MIGRATOR_PASSWORD:-d0_migrator_smoke}"
export D0_RUNTIME_PASSWORD="${D0_RUNTIME_PASSWORD:-d0_runtime_smoke}"
export INCUBIA_D0_PORT="${INCUBIA_D0_PORT:-18080}"

dc() {
  docker compose --project-name "$task_project" --file "$task_root/compose.yaml" "$@"
}

cleanup() {
  if [[ -n "$preflight_id" ]]; then
    docker rm --force "$preflight_id" >/dev/null 2>&1 || true
  fi
  dc down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

http_status() {
  local path=$1
  curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
    "http://127.0.0.1:${INCUBIA_D0_PORT}${path}" || true
}

wait_status() {
  local path=$1
  local expected=$2
  local attempts=30
  until [[ "$(http_status "$path")" == "$expected" ]]; do
    attempts=$((attempts - 1))
    if [[ "$attempts" -eq 0 ]]; then
      dc logs
      return 1
    fi
    sleep 1
  done
}

wait_ready() {
  wait_status /readyz 200
}

post() {
  local key=$1
  local conversation=$2
  local message=$3
  curl --fail --silent --show-error \
    -H 'Content-Type: application/json' \
    -H "Idempotency-Key: ${key}" \
    --data "{\"conversation_id\":\"${conversation}\",\"message\":\"${message}\"}" \
    "http://127.0.0.1:${INCUBIA_D0_PORT}/v1/executions"
}

assert_chain() {
  python3 - "$@" <<'PY'
import json
import sys

responses = [json.loads(value) for value in sys.argv[1:]]
assert [item["revision"] for item in responses[:3]] == [1, 2, 3], responses
assert len({item["execution_id"] for item in responses[:3]}) == 3, responses
assert {item["conversation_id"] for item in responses} == {"d0-chain"}, responses
assert [item["specialty"] for item in responses[:3]] == ["ventas", "marketing", "general"], responses
assert responses[3]["execution_id"] == responses[0]["execution_id"], responses
assert responses[3]["replayed"] is True, responses
assert responses[4]["revision"] == 4, responses
PY
}

assert_durable_counts() {
  local expected=$1
  local turns
  local outcomes
  local deliveries
  turns=$(dc exec -T postgres psql -U d0_migrator -d incubia_d0 -Atc \
    "SELECT count(*) FROM turns WHERE conversation_id = 'd0-chain'")
  outcomes=$(dc exec -T postgres psql -U d0_migrator -d incubia_d0 -Atc \
    "SELECT count(*) FROM outcomes o JOIN turns t USING (execution_id) WHERE t.conversation_id = 'd0-chain'")
  deliveries=$(dc exec -T postgres psql -U d0_migrator -d incubia_d0 -Atc \
    "SELECT count(*) FROM deliveries d JOIN turns t USING (execution_id) WHERE t.conversation_id = 'd0-chain'")
  [[ "$turns" == "$expected" ]]
  [[ "$outcomes" == "$expected" ]]
  [[ "$deliveries" == "$expected" ]]
}

cd "$task_root"
dc build
dc up -d postgres

for _ in $(seq 1 30); do
  if dc exec -T postgres pg_isready -U d0_migrator -d incubia_d0 >/dev/null; then
    break
  fi
  sleep 1
done

# Before migration, the database is reachable but readiness must remain false.
preflight_id=$(dc run --detach --service-ports --no-deps app)
wait_status /healthz 200
[[ "$(http_status /readyz)" == "503" ]]
docker stop "$preflight_id" >/dev/null
docker rm "$preflight_id" >/dev/null
preflight_id=""

dc up -d migrate
for _ in $(seq 1 30); do
  if [[ "$(dc ps --all --status exited --services migrate)" == "migrate" ]]; then
    break
  fi
  sleep 1
done
[[ "$(dc ps --all --status exited --services migrate)" == "migrate" ]]
migrate_id=$(dc ps -aq migrate)
[[ -n "$migrate_id" ]]
[[ "$(docker inspect --format '{{.State.ExitCode}}' "$migrate_id")" == "0" ]]

dc up -d app
wait_status /healthz 200
wait_ready
[[ "$(dc exec -T app id -u)" == "10001" ]]
[[ "$(docker network inspect --format '{{.Internal}}' "${task_project}_d0-internal")" == "false" ]]
[[ "$(docker network inspect --format '{{index .Options "com.docker.network.bridge.enable_ip_masquerade"}}' "${task_project}_d0-internal")" == "false" ]]

# A reachable process is not ready while PostgreSQL is unavailable.
dc stop postgres >/dev/null
wait_status /readyz 503
dc start postgres >/dev/null
wait_ready

one=$(post key-1 d0-chain 'necesito una venta')
two=$(post key-2 d0-chain 'quiero una campana de marketing')
three=$(post key-3 d0-chain 'hola')
replay=$(post key-1 d0-chain 'necesito una venta')

dc restart app >/dev/null
wait_ready
four=$(post key-4 d0-chain 'continuemos')
assert_chain "$one" "$two" "$three" "$replay" "$four"
assert_durable_counts 4

recovery_payload='{"conversation_id":"d0-recovery","message":"recupera"}'
recovery_hash=$(python3 - "$recovery_payload" <<'PY'
from hashlib import sha256
import sys

print(sha256(sys.argv[1].encode()).hexdigest())
PY
)
dc exec -T postgres psql -U d0_migrator -d incubia_d0 -v ON_ERROR_STOP=1 -c \
  "INSERT INTO inbox_events (deployment_id, tenant_id, channel, channel_account_ref, external_event_id, payload_hash, payload_json, request_id, execution_id, state) VALUES ('d0-local', 'd0-local-tenant', 'http', 'd0-http', 'recovery-key', '${recovery_hash}', '${recovery_payload}'::jsonb, '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002', 'PROCESSING')"
dc restart app >/dev/null
wait_ready
recovery_state=$(dc exec -T postgres psql -U d0_migrator -d incubia_d0 -Atc \
  "SELECT state FROM inbox_events WHERE external_event_id = 'recovery-key'")
[[ "$recovery_state" == "RECEIVED" ]]
recovered=$(post recovery-key d0-recovery recupera)
python3 - "$recovered" <<'PY'
import json
import sys

response = json.loads(sys.argv[1])
assert response["execution_id"] == "00000000-0000-4000-8000-000000000002"
assert response["replayed"] is False
PY

# SIGTERM must preserve the committed conversation. The replay verifies no
# second turn appears after a restart.
dc kill -s TERM app >/dev/null
dc start app >/dev/null
wait_ready
post_term_replay=$(post key-4 d0-chain 'continuemos')
python3 - "$four" "$post_term_replay" <<'PY'
import json
import sys

before, after = (json.loads(value) for value in sys.argv[1:])
assert after["execution_id"] == before["execution_id"]
assert after["replayed"] is True
PY
assert_durable_counts 4

identity_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: forged' \
  --data '{"conversation_id":"d0-chain","message":"hola","tenant_id":"forged"}' \
  "http://127.0.0.1:${INCUBIA_D0_PORT}/v1/executions")
[[ "$identity_status" == "400" ]]

if dc logs | grep --fixed-strings --quiet "$D0_MIGRATOR_PASSWORD"; then
  echo 'migration password appeared in logs' >&2
  exit 1
fi
if dc logs | grep --fixed-strings --quiet "$D0_RUNTIME_PASSWORD"; then
  echo 'runtime password appeared in logs' >&2
  exit 1
fi

echo "E3-D0-L smoke passed (project ${task_project})"
