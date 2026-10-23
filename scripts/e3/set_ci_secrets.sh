#!/usr/bin/env bash
# Carga los secrets del job `neon` de .github/workflows/ci.yml en el environment
# neon-e3 desde deploy/e3-neon.env (generado por neon_h1.py prepare). Los valores
# van por stdin a gh y nunca se imprimen.
set -euo pipefail

REPO="${REPO:-IncubiaLab/Incubia-ia-orchestator}"
ENV_NAME="${ENV_NAME:-neon-e3}"
SOURCE="${1:-deploy/e3-neon.env}"

[ -f "$SOURCE" ] || { echo "No existe $SOURCE; corre scripts/e3/neon_h1.py prepare" >&2; exit 2; }

value() {
  python3 - "$SOURCE" "$1" <<'EOF'
import sys
for line in open(sys.argv[1]):
    line = line.strip()
    if line.startswith(sys.argv[2] + "="):
        sys.stdout.write(line.split("=", 1)[1].strip().strip("'\""))
        break
else:
    sys.exit(f"{sys.argv[2]} no está en {sys.argv[1]}")
EOF
}

gh api -X PUT "repos/$REPO/environments/$ENV_NAME" --silent
for key in DATABASE_URL INCUBIA_MIGRATION_DATABASE_URL; do
  value "$key" | gh secret set "$key" --env "$ENV_NAME" --repo "$REPO"
done
if [ -n "${INCUBIA_E3_H1_BACKUP_EVIDENCE:-}" ]; then
  printf '%s' "$INCUBIA_E3_H1_BACKUP_EVIDENCE" | gh secret set INCUBIA_E3_H1_BACKUP_EVIDENCE --env "$ENV_NAME" --repo "$REPO"
fi
gh secret list --env "$ENV_NAME" --repo "$REPO"
