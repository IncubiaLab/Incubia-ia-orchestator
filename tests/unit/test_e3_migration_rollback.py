"""E3-5: regla expand/contract que hace posible el rollback de imagen.

Las migraciones son forward-only.  Un rollback de app (imagen N -> N-1) solo
es seguro si el esquema N sigue siendo compatible con la app N-1; por eso
toda migración debe ser aditiva salvo pasos *contract* documentados aquí.
Ver docs/roadmap/etapa-3/RUNBOOK.md, sección "Rollback".
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIRS = ("migrations/postgres", "migrations/knowledge")

# Patrones que rompen a la versión anterior de la app (o pierden datos).
DESTRUCTIVE = (
    re.compile(r"\bDROP\s+(TABLE|COLUMN|SCHEMA|INDEX|VIEW|TYPE|FUNCTION|TRIGGER|ROLE)\b", re.I),
    re.compile(r"\bALTER\s+TABLE\b.*\bDROP\b", re.I | re.S),
    re.compile(r"\bRENAME\b", re.I),
    re.compile(r"\bTRUNCATE\b", re.I),
    re.compile(r"\bALTER\s+COLUMN\b.*\b(TYPE|SET\s+NOT\s+NULL)\b", re.I | re.S),
    re.compile(r"^\s*DELETE\s+FROM\b", re.I | re.M),
)

# Pasos contract aceptados, congelados.  Todos son pre-release (no existía una
# app N-1 que escribiera esas filas sin scope) y van precedidos de backfill en
# la misma migración.  Una migración nueva NO puede agregarse aquí sin una
# entrada en RUNBOOK "Rollback" que declare la versión de app mínima.
CONTRACT_STEPS = {
    "002_e3_h1_rls.sql": 4,
    "006_e3_d0_runtime_claims.sql": 4,
}
CONTRACT_BASELINE = 7  # migraciones postgres <= 007 forman el baseline E3.


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _statements(sql: str) -> list[str]:
    # Suficiente para estos archivos: los bloques DO $$ ... $$ no contienen DDL destructivo.
    return [s.strip() for s in _strip_comments(sql).split(";") if s.strip()]


def _migrations() -> list[Path]:
    files = []
    for directory in MIGRATION_DIRS:
        files.extend(sorted((ROOT / directory).glob("*.sql")))
    return files


def _destructive(statement: str) -> bool:
    return any(pattern.search(statement) for pattern in DESTRUCTIVE)


def test_migration_files_exist_and_are_numbered_contiguously():
    for directory in MIGRATION_DIRS:
        files = sorted((ROOT / directory).glob("*.sql"))
        assert files, directory
        numbers = [int(f.name.split("_", 1)[0]) for f in files]
        assert numbers == list(range(1, len(files) + 1)), directory


@pytest.mark.parametrize("path", _migrations(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_migration_is_additive_or_documented_contract(path: Path):
    statements = _statements(path.read_text(encoding="utf-8"))
    destructive = [s for s in statements if _destructive(s)]
    allowed = CONTRACT_STEPS.get(path.name, 0) if path.parent.name == "postgres" else 0
    assert len(destructive) == allowed, (
        f"{path.name}: paso no aditivo sin contract documentado; "
        f"usar expand/contract (RUNBOOK Rollback): {destructive}"
    )


def test_contract_allowlist_is_frozen_to_the_baseline():
    for name in CONTRACT_STEPS:
        assert int(name.split("_", 1)[0]) <= CONTRACT_BASELINE
        assert (ROOT / "migrations/postgres" / name).exists()


def test_contract_set_not_null_is_preceded_by_backfill():
    for name in CONTRACT_STEPS:
        statements = _statements((ROOT / "migrations/postgres" / name).read_text(encoding="utf-8"))
        for index, statement in enumerate(statements):
            match = re.search(r"ALTER\s+TABLE\s+(\w+)\s+ALTER\s+COLUMN\s+(\w+)\s+SET\s+NOT\s+NULL", statement, re.I)
            if not match:
                continue
            table, column = match.groups()
            before = statements[:index]
            assert any(re.search(rf"UPDATE\s+{table}\b.*\b{column}\b", s, re.I | re.S) for s in before), (
                name,
                table,
                column,
            )


@pytest.mark.parametrize("path", _migrations(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_dropped_policies_are_recreated_in_the_same_migration(path: Path):
    sql = _strip_comments(path.read_text(encoding="utf-8"))
    dropped = re.findall(r"DROP\s+POLICY\s+IF\s+EXISTS\s+(\w+)\s+ON\s+(\w+)", sql, re.I)
    created = set(re.findall(r"CREATE\s+POLICY\s+(\w+)\s+ON\s+(\w+)", sql, re.I))
    for policy in dropped:
        assert policy in created, f"{path.name}: {policy} se elimina sin recrearse"


def test_schema_changes_are_idempotent_for_reapply_after_restore():
    # Tras restore a una rama/DB previa se re-aplica la cadena; CREATE/ADD deben tolerarlo.
    for path in _migrations():
        for statement in _statements(path.read_text(encoding="utf-8")):
            if re.match(r"CREATE\s+(UNIQUE\s+)?(TABLE|INDEX)\b", statement, re.I):
                assert re.search(r"IF\s+NOT\s+EXISTS", statement, re.I), (path.name, statement[:80])
            if re.search(r"ADD\s+COLUMN\b", statement, re.I):
                assert re.search(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", statement, re.I), (path.name, statement[:80])


def test_runbook_documents_rollback_procedure():
    runbook = (ROOT / "docs/roadmap/etapa-3/RUNBOOK.md").read_text(encoding="utf-8")
    assert "### Rollback" in runbook
    for needle in ("expand/contract", "h1_backup.py", "test_e3_migration_rollback.py", "imagen"):
        assert needle in runbook, needle
