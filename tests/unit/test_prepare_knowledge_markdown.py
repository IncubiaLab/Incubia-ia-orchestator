import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "prepare_knowledge_markdown",
    Path(__file__).resolve().parents[2] / "scripts/e3/prepare_knowledge_markdown.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_markdown_bundle_preserves_structure_and_provenance(tmp_path):
    source = tmp_path / "document.md"
    source.write_bytes(b"\xef\xbb\xbf# Title\r\n\r\n```python\r\n    x = 1  \r\n```\r\n")
    kwargs = dict(deployment_id="incubialab", source_id="drive:file-1", source_version="v1")
    manifest = module.prepare(source, tmp_path / "bundles", **kwargs)
    markdown = (manifest.parent / "document.md").read_bytes()
    metadata = json.loads(manifest.read_text())
    assert b"    x = 1  \n" in markdown
    assert metadata["source_sha256"] == sha256(source.read_bytes()).hexdigest()
    assert metadata["markdown_sha256"] == sha256(markdown).hexdigest()
    assert metadata["ingest_ready"] is False
    assert metadata["acl_review"] == "pending"
    assert module.prepare(source, tmp_path / "bundles", **kwargs) == manifest
    other = module.prepare(source, tmp_path / "bundles", **(kwargs | {"deployment_id": "other"}))
    assert other.parent != manifest.parent


@pytest.mark.parametrize("filename,content,max_bytes", [
    ("empty.md", b" \n", 100),
    ("large.md", b"x" * 101, 100),
    ("archive.zip", b"content", 100),
    ("invalid.md", b"\x00text", 100),
])
def test_invalid_inputs_do_not_create_a_bundle(tmp_path, filename, content, max_bytes):
    source = tmp_path / filename
    source.write_bytes(content)
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        module.prepare(source, output, deployment_id="d", source_id="s", source_version="v",
                       max_bytes=max_bytes)
    assert not output.exists()
