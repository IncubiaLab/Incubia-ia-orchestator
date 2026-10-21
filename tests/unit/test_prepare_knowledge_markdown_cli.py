"""Additional behaviour contract for scripts/e3/prepare_knowledge_markdown.py.

These tests extend (and never modify) the pinned contract in
tests/unit/test_prepare_knowledge_markdown.py. Every bundle created here is
written under pytest's tmp_path, never inside the repository working tree.
"""
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/e3/prepare_knowledge_markdown.py"

spec = importlib.util.spec_from_file_location("prepare_knowledge_markdown_cli", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _kwargs(**overrides):
    base = dict(deployment_id="incubialab", source_id="drive:file-1", source_version="v1")
    base.update(overrides)
    return base


# --- Private-directory containment -----------------------------------------

def test_output_dir_inside_repo_is_rejected(tmp_path):
    source = tmp_path / "document.md"
    source.write_bytes(b"# hello\n")
    inside_repo = REPO_ROOT / "tmp-rag-v1-offline-test-bundle"
    assert not inside_repo.exists()
    try:
        with pytest.raises(ValueError):
            module.prepare(source, inside_repo, **_kwargs())
        assert not inside_repo.exists()
    finally:
        if inside_repo.exists():
            inside_repo.rmdir()


# --- Restrictive permissions -------------------------------------------------

def test_bundle_directories_and_files_get_restrictive_modes(tmp_path):
    source = tmp_path / "document.md"
    source.write_bytes(b"# hello\n")
    manifest = module.prepare(source, tmp_path / "bundles", **_kwargs())
    document = manifest.parent / "document.md"

    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    assert stat.S_IMODE(document.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest.parent.stat().st_mode) == 0o700


# --- Source must be a regular file, not a symlink ---------------------------

def test_symlink_source_is_rejected(tmp_path):
    real = tmp_path / "real.md"
    real.write_bytes(b"# hello\n")
    link = tmp_path / "link.md"
    os.symlink(real, link)
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        module.prepare(link, output, **_kwargs())
    assert not output.exists()


# --- Manifest provenance fields ---------------------------------------------

def test_manifest_carries_full_provenance(tmp_path):
    source = tmp_path / "document.md"
    source.write_bytes(b"# hello\n")
    manifest = module.prepare(
        source, tmp_path / "bundles",
        **_kwargs(source_url="https://drive.example/file-1"),
    )
    metadata = json.loads(manifest.read_text())
    assert metadata["deployment_id"] == "incubialab"
    assert metadata["source_id"] == "drive:file-1"
    assert metadata["source_version"] == "v1"
    assert metadata["source_url"] == "https://drive.example/file-1"
    assert isinstance(metadata["converter_version"], str) and metadata["converter_version"]
    assert isinstance(metadata["pipeline_version"], str) and metadata["pipeline_version"]
    assert metadata["source_bytes"] == len(source.read_bytes())
    assert metadata["markdown_bytes"] == (manifest.parent / "document.md").stat().st_size
    assert metadata["extraction_review"] == "pending"
    assert metadata["acl_review"] == "pending"
    assert metadata["ingest_ready"] is False
    generated_at = metadata["generated_at"]
    assert generated_at.endswith("+00:00") or generated_at.endswith("Z")


def test_manifest_source_url_defaults_to_null(tmp_path):
    source = tmp_path / "document.md"
    source.write_bytes(b"# hello\n")
    manifest = module.prepare(source, tmp_path / "bundles", **_kwargs())
    metadata = json.loads(manifest.read_text())
    assert metadata["source_url"] is None


@pytest.mark.parametrize("acl_review,extraction_review,expected", [
    ("pending", "pending", False),
    ("approved", "pending", False),
    ("pending", "approved", False),
    ("approved", "approved", True),
])
def test_ingest_ready_is_false_whenever_either_review_is_pending(acl_review, extraction_review, expected):
    assert module.ingest_ready_from_reviews(
        acl_review=acl_review, extraction_review=extraction_review
    ) is expected


# --- No secret echo -----------------------------------------------------------

def test_oversized_file_error_does_not_echo_the_temp_path(tmp_path):
    source = tmp_path / "large.md"
    source.write_bytes(b"x" * 101)
    output = tmp_path / "output"
    with pytest.raises(ValueError) as excinfo:
        module.prepare(source, output, **_kwargs(), max_bytes=100)
    assert str(tmp_path) not in str(excinfo.value)
    assert not output.exists()


# --- CLI -----------------------------------------------------------------------

def test_cli_main_success_prints_manifest_path_and_returns_zero(tmp_path, capsys):
    source = tmp_path / "document.md"
    source.write_bytes(b"# hello\n")
    output_dir = tmp_path / "bundles"
    rc = module.main([
        str(source),
        "--output-dir", str(output_dir),
        "--deployment-id", "incubialab",
        "--source-id", "drive:file-1",
        "--source-version", "v1",
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    printed = Path(out)
    assert printed.is_file()
    assert printed.name == "manifest.json"
    assert printed.is_relative_to(output_dir)


def test_cli_main_failure_returns_two_and_prints_sanitized_reason(tmp_path, capsys):
    source = tmp_path / "archive.zip"
    source.write_bytes(b"content")
    output_dir = tmp_path / "bundles"
    rc = module.main([
        str(source),
        "--output-dir", str(output_dir),
        "--deployment-id", "incubialab",
        "--source-id", "drive:file-1",
        "--source-version", "v1",
    ])
    assert rc == 2
    err = capsys.readouterr().err.strip()
    assert "not implemented in V1" in err
    assert str(tmp_path) not in err
    assert not output_dir.exists()


def test_cli_main_accepts_optional_source_url_and_max_bytes(tmp_path):
    source = tmp_path / "document.md"
    source.write_bytes(b"# hello\n")
    output_dir = tmp_path / "bundles"
    rc = module.main([
        str(source),
        "--output-dir", str(output_dir),
        "--deployment-id", "incubialab",
        "--source-id", "drive:file-1",
        "--source-version", "v1",
        "--source-url", "https://drive.example/file-1",
        "--max-bytes", "1000",
    ])
    assert rc == 0


# --- Unsupported types refused by extension AND content sniff -----------------

def test_unsupported_extension_other_than_zip_is_refused(tmp_path):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 not really a pdf")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="not implemented in V1"):
        module.prepare(source, output, **_kwargs())
    assert not output.exists()


def test_accepted_extension_with_invalid_utf8_content_is_refused_by_sniff(tmp_path):
    source = tmp_path / "binary.txt"
    source.write_bytes(b"\xff\xfe\x00\x01not text")
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        module.prepare(source, output, **_kwargs())
    assert not output.exists()
