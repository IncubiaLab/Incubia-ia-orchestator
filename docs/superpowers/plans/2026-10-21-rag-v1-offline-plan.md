# Plan — RAG-V1 offline slice (Drive contracts, Markdown converter, remote guards)

Date: 2026-10-21. Spec authority: `docs/roadmap/etapa-3/dessing.md` §11 and
`docs/roadmap/etapa-3/howto.md` §10.1. Acceptance criteria: `docs/roadmap/etapa-3/GOALS.md`
(«Feature RAG IncubiaLab», row `1 / RAG-V1`).

This plan covers the **offline** portion of RAG-V1 only. It does not and cannot
close RAG-V1: that requires real Drive and Neon evidence which this work is
forbidden from gathering.

## Global Constraints

These bind every task. A reviewer must treat a violation as Critical.

1. **No credentials, no network.** No Google Drive SDK, no Neon connection, no
   provider HTTP call, no reading of `.env`, `.neon`, `deploy/*.env`, or any
   secret. All I/O in tests goes through injected fakes. The repository's
   offline harness (`tests/conftest.py`) blocks sockets and must not be
   weakened, bypassed, or marked around.
2. **Do not touch the user's documents.** `docs/roadmap/**`, `docs/adr/**`, and
   `docs/specs/**` are read-only inputs. Never `git reset`, `git stash`,
   `git stash apply`, `git checkout --`, `git commit`, or `git add`. The
   stash entry `stash@{0}` must never be applied or popped.
3. **Strict red-green TDD.** For every behaviour: write/observe the failing test
   first, record its failure output, then write the minimum code to pass, then
   record the passing output. Never write implementation before a failing test
   exists for it.
4. **Neon branch `production` is prohibited.** The user named branch
   `production`; this work must *reject* it. Guards reject `production`,
   `main`, `master`, empty, and unset branch names, and require an explicitly
   named dedicated isolated branch.
5. **Drive identity is undecided.** Model it as a port with a fail-closed
   preflight contract. Absent, unverified, or unrecognised identity = deny.
   Never pick an identity mechanism (OAuth user vs service account) in code.
6. **Private artifacts live outside Git.** The converter writes only to a
   caller-supplied directory that must resolve outside the repository working
   tree, created with mode `0700`. Never create corpus, export, or manifest
   files inside the repo. No test may write a bundle into the repo.
7. **No new dependencies** unless genuinely required and pinned exactly in
   `pyproject.toml` plus the lock. Standard library is preferred. MarkItDown is
   explicitly out of scope for V1.
8. **Follow existing style.** Frozen dataclasses with `__post_init__`
   validation, `Protocol` ports, typed errors, sanitized messages (never echo a
   DSN, token, path secret, or provider traceback). See
   `modules/orchestration/adapters/tools/openfoodfacts.py` and
   `scripts/e3/run_neon_h1.py` as reference style.
9. **Scope ceiling.** V1 only. No V2 schema/migration/chunking/embedding/
   ingestion work. No V3 sync/changes/leases/caches. No modification of
   `migrations/`, `modules/knowledge/adapters/postgres.py`, or
   `application/ingest.py`.
10. **No status inflation.** Nothing in code, docstrings, or docs may claim
    RAG-V1 is validated, `lista_para_validacion`, or that a real corpus is
    connected.

Verification commands (run from repo root with `.venv/bin/python`):

```bash
.venv/bin/python -m pytest tests/unit/test_prepare_knowledge_markdown.py -q
.venv/bin/python -m pytest tests/unit/test_drive_source_catalog.py -q
.venv/bin/python -m pytest tests/unit/test_neon_branch_guard.py -q
.venv/bin/python -m pytest tests/test_boundaries.py tests/test_cli_offline.py tests/unit -q
```

---

## Task 1 — Markdown converter CLI and manifest

**Status at start: RED is already observed.**
`tests/unit/test_prepare_knowledge_markdown.py` fails at collection with
`FileNotFoundError: .../scripts/e3/prepare_knowledge_markdown.py`. That file is
the pre-existing, authoritative behaviour contract. Do not edit it.

Create `scripts/e3/prepare_knowledge_markdown.py`.

### Required API

```python
def prepare(source: Path, output_dir: Path, *, deployment_id: str, source_id: str,
            source_version: str, source_url: str | None = None,
            max_bytes: int = 25 * 1024 * 1024) -> Path
```

Returns the path to the written `manifest.json`.

### Behaviour the existing test pins

- Input `b"\xef\xbb\xbf# Title\r\n\r\n\`\`\`python\r\n    x = 1  \r\n\`\`\`\r\n"`
  must produce Markdown containing the exact bytes `b"    x = 1  \n"`.
  That means: strip a leading UTF-8 BOM, normalise CRLF and lone CR to LF, and
  **preserve all other whitespace**, including trailing spaces inside code
  fences. Do not re-wrap, re-indent, or strip trailing whitespace.
- `manifest.json` is JSON with at least:
  `source_sha256` = SHA-256 hex of the raw input bytes;
  `markdown_sha256` = SHA-256 hex of the written `document.md` bytes;
  `ingest_ready` is the JSON literal `false`;
  `acl_review` is the string `"pending"`.
- `document.md` is written as a sibling of `manifest.json`
  (`manifest.parent / "document.md"`).
- Calling `prepare` twice with identical arguments returns the **same** path and
  must not raise. Re-running is idempotent.
- Changing `deployment_id` must yield a **different** `manifest.parent`.
- These inputs must raise `ValueError` **and leave the output directory
  non-existent** (`assert not output.exists()`), with `max_bytes=100`:
  `(" \n")` empty-after-strip; `b"x" * 101` oversized; `archive.zip`
  unsupported extension; `b"\x00text"` NUL byte / not valid UTF-8 text.
  Therefore: perform **all** validation before creating any directory.

### Additional required behaviour (write a new failing test first for each)

Put new tests in `tests/unit/test_prepare_knowledge_markdown_cli.py` — do not
modify the existing test file.

- **Private-directory containment.** If `output_dir` resolves to a path inside
  the repository working tree (the directory containing `.git`, found by
  walking up from the script), raise `ValueError` and create nothing. Resolve
  symlinks before comparing.
- **Restrictive permissions.** Directories the converter creates get mode
  `0o700`; `document.md` and `manifest.json` get mode `0o600`. Assert with
  `stat.S_IMODE`.
- **Source must be a regular file, not a symlink.** `Path.is_symlink()` or a
  non-regular file raises `ValueError`, creating nothing.
- **Manifest provenance fields.** Beyond the four pinned keys the manifest must
  carry: `deployment_id`, `source_id`, `source_version`, `source_url` (null when
  not given), `converter_version`, `pipeline_version`, `source_bytes`,
  `markdown_bytes`, `extraction_review` = `"pending"`, and `generated_at` as an
  ISO-8601 UTC timestamp. `extraction_review` and `acl_review` are both
  `"pending"`, which is why `ingest_ready` is `false`; encode that relationship
  in code, not as a hardcoded constant alone — a test must show that
  `ingest_ready` is false whenever either review is pending.
- **No secret echo.** Error messages must not include the full input path or
  output path contents; they name the condition, not the location. Add a test
  asserting the message for an oversized file does not contain the temp
  directory path string.
- **CLI.** `main(argv)` parsing exactly:
  `prepare_knowledge_markdown.py INPUT --output-dir DIR --deployment-id ID
  --source-id ID --source-version V [--source-url URL] [--max-bytes N]`.
  Returns `0` on success and prints the manifest path. Returns `2` on
  `ValueError`, printing a sanitized one-line reason to stderr. Add tests for
  both, invoking `main` directly (not a subprocess — the offline harness blocks
  subprocesses in places and a subprocess would be slower and less precise).
- **Unsupported types are refused by extension AND content sniff.** Only
  `.md`, `.markdown`, `.txt` are accepted in V1. Everything else raises
  `ValueError` with a message that says conversion for that type is not
  implemented in V1 — do **not** silently emit an empty or partial bundle.

### Bundle layout

`output_dir / <deployment_id slug> / <source_id digest> / <source_version slug> /`
containing `document.md` and `manifest.json`. Slugs must be filesystem-safe:
`source_id` arrives as e.g. `drive:file-1`, so derive the directory component
from a sanitized prefix plus a SHA-256 digest of the raw value so distinct ids
never collide. `deployment_id` must differ in the path when it differs (pinned
by the existing test).

### Files

- create `scripts/e3/prepare_knowledge_markdown.py`
- create `tests/unit/test_prepare_knowledge_markdown_cli.py`
- do not modify `tests/unit/test_prepare_knowledge_markdown.py`

---

## Task 2 — Sanitized read-only Drive inventory and export contracts

Model the Drive source catalog as ports with a paginated fake transport. No
Google SDK, no HTTP client, no credentials.

### Domain values — add to `src/incubia_orchestrator/modules/knowledge/domain.py`

Frozen dataclasses with `__post_init__` validation, matching the existing file's
style. Do not alter `Source`, `EvidenceItem`, or `RetrievalQuery`.

- `SourceRef`: `source_id`, `name`, `mime_type`, `parents: tuple[str, ...]`,
  `observed_version`, `modified_time: datetime`, `size_bytes: int | None`,
  `trashed: bool = False`, `shortcut_target_id: str | None = None`.
  Validates non-empty ids/mime, non-negative size, at least one parent.
- `InventoryPage`: `items: tuple[SourceRef, ...]`, `next_page_token: str | None`.
- `InventoryEntry`: the sanitized inventory record — `SourceRef` plus
  `root_id`, `depth`, `classification`, `acl_state`. `acl_state` defaults to
  the unknown/deny value.
- `AclState(StrEnum)`: `UNKNOWN`, `PENDING_REVIEW`, `VERIFIED`, `DENIED`.
  `UNKNOWN` is the default and is treated as deny.
- `ExportRequest`: `source_id`, `mime_type`, `target_mime_type`, `max_bytes`.
- `ExportResult`: `source_id`, `target_mime_type`, `content: bytes`,
  `sha256`, `truncated: bool` — `truncated=True` must be rejected in
  `__post_init__`; V1 never accepts a truncated export.
- `SourceCatalogError(Exception)` subclasses with sanitized messages:
  `RootContainmentError`, `IdentityNotVerifiedError`, `InventoryLimitError`,
  `ExportTooLargeError`, `UnsupportedExportError`.

### Ports — add to `src/incubia_orchestrator/modules/knowledge/ports.py`

- `DriveTransportPort(Protocol)`: `list_children(folder_id, page_token) ->
  InventoryPage`, `get_metadata(source_id) -> SourceRef`,
  `export(request: ExportRequest) -> ExportResult`. This is the seam the fake
  implements and the real adapter will later implement with the SDK.
- `DriveIdentityPort(Protocol)`: `assert_verified() -> VerifiedIdentity`.
  `VerifiedIdentity` is a frozen value carrying an opaque `principal_digest`
  (never an email) and `granted_scopes: tuple[str, ...]`. Raising or returning
  anything unverified is a deny.
- `SourceCatalogPort(Protocol)`: `inventory(root_id) ->
  tuple[InventoryEntry, ...]`, `export_document(entry) -> ExportResult`.

### Adapter — create `src/incubia_orchestrator/modules/knowledge/adapters/drive_catalog.py`

`DriveSourceCatalog(SourceCatalogPort)` taking `transport`, `identity`, and a
frozen `DriveCatalogConfig(max_documents=..., max_depth=..., max_pages=...,
max_export_bytes=..., allowed_export_mime_types=...)`.

Required behaviour:

- **Fail-closed identity preflight.** `inventory` and `export_document` call
  `identity.assert_verified()` *first*. If it raises or yields unverified,
  raise `IdentityNotVerifiedError` and perform **zero** transport calls. A test
  must assert the fake transport's call counter is `0`.
- **Full pagination.** Follow `next_page_token` until `None`; all pages'
  items appear in the result. Fake must return at least 3 pages in the test.
- **Root containment.** Every returned entry's ancestor chain must terminate at
  `root_id`. An item whose `parents` do not lead back to the root is excluded
  with a cause, and an item that claims the root but whose parent chain escapes
  raises `RootContainmentError`. A test must cover a folder that is a sibling
  of the root.
- **Visited set.** A parent cycle must terminate, not recurse forever. Test with
  a fake whose folder A contains folder B which contains folder A.
- **Depth and document caps.** Exceeding `max_depth`, `max_documents`, or
  `max_pages` raises `InventoryLimitError`; it does not silently truncate.
- **Trashed excluded.** `trashed=True` items never appear.
- **Shortcuts.** A `shortcut_target_id` is resolved via `get_metadata`; if the
  target is not contained in the root it is excluded with a cause and never
  followed. Never follow a shortcut outside the root.
- **ACL unknown by default.** Every `InventoryEntry` is produced with
  `acl_state=AclState.UNKNOWN`. The adapter never upgrades ACL state on its
  own — authorization is a separate, undecided decision.
- **Export is read-only and bounded.** `export_document` rejects a target MIME
  not in `allowed_export_mime_types` (`UnsupportedExportError`), rejects content
  over `max_export_bytes` (`ExportTooLargeError`), rejects `truncated=True`, and
  verifies the returned `sha256` against the bytes — a mismatch raises. Default
  allowed targets: `text/markdown`,
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
  `application/vnd.openxmlformats-officedocument.presentationml.presentation`.
  Never `text/csv` (loses sheets).
- **Sanitized errors.** No message contains a file name, a URL, or a transport
  exception's text. Add a test for this.

### Fake — create `tests/fakes/drive_transport.py`

A deterministic in-memory `FakeDriveTransport` built from a dict of folders and
files, with a configurable `page_size` so pagination is exercised, and public
counters (`list_calls`, `metadata_calls`, `export_calls`) so tests can assert
zero-call denials. Follow the style of `tests/fakes/channel_delivery.py`.

### Tests — create `tests/unit/test_drive_source_catalog.py`

Behaviour tests, one per bullet above. Red first, then green.

### Files

- modify `src/incubia_orchestrator/modules/knowledge/domain.py` (additive only)
- modify `src/incubia_orchestrator/modules/knowledge/ports.py` (additive only)
- create `src/incubia_orchestrator/modules/knowledge/adapters/drive_catalog.py`
- create `tests/fakes/drive_transport.py`
- create `tests/unit/test_drive_source_catalog.py`

---

## Task 3 — Remote campaign and preflight guards

The user supplied Neon branch `production`. This task makes that branch
impossible to use and requires a named dedicated isolated branch instead.

### Create `scripts/e3/neon_branch_guard.py`

Pure, importable, no network, no subprocess at import time.

```python
PROHIBITED_BRANCHES = frozenset({"production", "prod", "main", "master", "default"})

class BranchGuardError(ValueError): ...

def require_isolated_branch(name: str | None, *, expected: str | None = None) -> str
```

Behaviour:

- `None`, `""`, or whitespace → `BranchGuardError` ("a dedicated isolated Neon
  branch must be named explicitly").
- Case-insensitive, whitespace-stripped match against `PROHIBITED_BRANCHES` →
  `BranchGuardError` naming the rejection reason without echoing anything else.
  `"Production"`, `" production "`, and `"PRODUCTION"` all reject.
- A name that is not a safe branch slug (`^[a-z0-9][a-z0-9-]{2,62}$` after
  lowering) → `BranchGuardError`.
- When `expected` is given and differs → `BranchGuardError`.
- Otherwise returns the normalised name.

Also:

```python
def guard_campaign_environment(env: Mapping[str, str], *, expected_branch: str,
                               authorization_flag: str = "INCUBIA_E3_NEON_TESTS") -> str
```

- Requires `env[authorization_flag] == "1"`, else `BranchGuardError`.
- Requires `env["INCUBIA_E3_NEON_BRANCH"]` to pass `require_isolated_branch`
  against `expected_branch`.
- Returns the validated branch name.

```python
def sanitize_dsn_reference(dsn: str) -> str
```

- Returns `"<scheme>://<user>@<host-digest>/<database>"` style identity with the
  host replaced by a short SHA-256 digest and **no** password, no query string,
  no port. Raises `BranchGuardError` for a non-postgres scheme, for an embedded
  password that cannot be removed, or for a host not ending in `.neon.tech`.
- A test must assert that a DSN containing `password=hunter2` and
  `?sslmode=require&options=secret` produces output containing none of those
  substrings.

### Create `scripts/e3/run_rag_v1_preflight.py`

A fail-closed preflight runner for RAG-V1. It performs **no** network calls in
this slice; it validates the environment contract and refuses otherwise.

- `main(argv=None, env=None) -> int`.
- Requires `--branch` naming the dedicated isolated branch; passes it through
  `guard_campaign_environment`.
- Requires `--private-artifact-dir` that resolves outside the repository and is
  mode `0700`; otherwise refuses.
- Requires a Drive identity preflight assertion to be explicitly declared
  unresolved: because Drive identity is undecided, the runner always reports
  `drive_identity: UNRESOLVED` and returns a non-zero "not ready" code rather
  than pretending readiness.
- Prints a sanitized report (no DSN, no token, no path outside what the user
  passed) and returns `0` only when every check passes — which, given
  `drive_identity: UNRESOLVED`, it currently cannot. Encode that honestly: the
  runner returns `3` meaning `requiere_cambios`, and a test pins that.

### Wire the existing runner

`scripts/e3/run_neon_h1.py` currently compares `INCUBIA_E3_NEON_BRANCH` to a
literal. Replace that literal comparison with `guard_campaign_environment(...,
expected_branch="e3-h1-synthetic")` so the prohibited-branch rejection applies
there too. Keep its existing exit codes and sanitized messages. Do not change
any other behaviour in that file, and do not run it.

### Tests — create `tests/unit/test_neon_branch_guard.py`

One behaviour per bullet, red first. Include a case asserting that
`require_isolated_branch("production")` raises — this is the explicit guard the
user asked for.

### Files

- create `scripts/e3/neon_branch_guard.py`
- create `scripts/e3/run_rag_v1_preflight.py`
- modify `scripts/e3/run_neon_h1.py` (branch-guard call only)
- create `tests/unit/test_neon_branch_guard.py`
- create `tests/unit/test_rag_v1_preflight.py`

---

## Task 4 — Security review of the slice

Adversarial read of everything Tasks 1-3 produced, against the Global
Constraints. Report findings; do not fix.
