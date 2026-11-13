"""Apply 003_knowledge_access_tier.sql and backfill access_tier on existing knowledge_sources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/knowledge/003_knowledge_access_tier.sql"
DEFAULT_ENV_FILE = ROOT / "deploy/knowledge-neon.env"

_CAPA3_DRIVE_RE = re.compile(
    r"\b(manual(?:es)?|brand\s*book|brand\s*guidelines|stack(?:\s*tecnologico)?|guia\s+de\s+uso|onboarding)\b"
)
_CAPA3_LINEAR_RE = re.compile(
    r"^(\[linear|hec\s+\d+|adr\b|rag\s+incubialab|borrador\s+sad\b|incubia\s+mvp\s+adr\s+register|howto\.md\b)"
)
_CAPA2_SENSITIVE_RE = re.compile(
    r"\b(requerimiento|nfr(?:s)?|srs|legal|contrato|confidencial|acta|propuesta|cpanel|enlace\s+y\s+usuario)\b"
)


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text)
    plain = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"[_—–-]+", " ", plain).strip()


def classify_public_ref(raw_ref: str | None) -> str:
    """Classify an existing source into workspace_general (Capa 3) or admin_only (Capa 2)."""
    if not raw_ref:
        return "admin_only"
    title = raw_ref
    try:
        parsed = json.loads(raw_ref)
        if isinstance(parsed, dict) and parsed.get("title"):
            title = str(parsed["title"])
    except Exception:
        pass
    norm = _normalize(title)
    if _CAPA2_SENSITIVE_RE.search(norm):
        return "admin_only"
    if _CAPA3_LINEAR_RE.search(norm) or _CAPA3_DRIVE_RE.search(norm):
        return "workspace_general"
    return "admin_only"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--apply", action="store_true", help="Apply migration and backfill access_tier")
    parser.add_argument("--backfill-only", action="store_true", help="Only backfill access_tier using ingest DSN")
    args = parser.parse_args(argv)

    if not args.env_file.is_file():
        print(f"error: env file not found: {args.env_file}", file=sys.stderr)
        return 2
    env = _load_env_file(args.env_file)
    migrator_dsn = env.get("INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL", "")
    ingest_dsn = env.get("INCUBIA_KNOWLEDGE_INGEST_DATABASE_URL", "")
    if not ingest_dsn or (args.apply and not args.backfill_only and not migrator_dsn):
        print("error: missing migration or ingest DSN in env file", file=sys.stderr)
        return 2

    import psycopg

    if not args.apply and not args.backfill_only:
        with psycopg.connect(ingest_dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT source_id, public_ref FROM knowledge_sources WHERE revoked_at IS NULL"
                )
                rows = cur.fetchall()
        counts = {"workspace_general": 0, "admin_only": 0}
        for _src_id, raw_ref in rows:
            counts[classify_public_ref(raw_ref)] += 1
        print(f"dry-run ok: active_sources={len(rows)} classification={counts}")
        return 0

    if not args.backfill_only:
        with psycopg.connect(migrator_dsn, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(MIGRATION.read_text())
            conn.commit()
        print("migration 003_knowledge_access_tier.sql applied")

    with psycopg.connect(ingest_dsn, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_id, public_ref FROM knowledge_sources WHERE revoked_at IS NULL"
            )
            rows = cur.fetchall()
            counts = {"workspace_general": 0, "admin_only": 0}
            for src_id, raw_ref in rows:
                tier = classify_public_ref(raw_ref)
                counts[tier] += 1
                cur.execute(
                    "UPDATE knowledge_sources SET access_tier = %s WHERE source_id = %s",
                    (tier, src_id),
                )
        conn.commit()
    print(f"backfill ok: active_sources={len(rows)} classification={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

