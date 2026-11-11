import pytest

from scripts.e3.ingest_drive_knowledge import ROOT, ConfigError, drive_config, main


def _env(tmp_path, **overrides):
    env = {"INCUBIA_KNOWLEDGE_NEON_BRANCH": "feat-knowledge-base",
           "INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE": str(tmp_path / "sa.json"),
           "INCUBIA_DRIVE_ROOT_FOLDER_ID": "1IiwcAQpeY-OeK9EwkS9oJnfMxw653kun",
           "INCUBIA_KNOWLEDGE_DEPLOYMENT_ID": "incubialab"}
    env.update(overrides)
    return env


def test_valid_config(tmp_path):
    key, root, deployment = drive_config(_env(tmp_path))
    assert key.name == "sa.json" and deployment == "incubialab" and root.startswith("1Iiw")


@pytest.mark.parametrize("overrides", [
    {"INCUBIA_KNOWLEDGE_NEON_BRANCH": "production"},
    {"INCUBIA_DRIVE_ROOT_FOLDER_ID": ""},
    {"INCUBIA_KNOWLEDGE_DEPLOYMENT_ID": ""},
    {"INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE": ""},
])
def test_refuses_incomplete_or_unsafe_config(tmp_path, overrides):
    with pytest.raises(ConfigError):
        drive_config(_env(tmp_path, **overrides))


def test_refuses_key_inside_repository(tmp_path):
    with pytest.raises(ConfigError):
        drive_config(_env(tmp_path, INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE=str(ROOT / "sa.json")))


def test_apply_requires_acl_review(tmp_path, capsys):
    env_file = tmp_path / "k.env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in _env(tmp_path).items()))
    assert main(["--env-file", str(env_file), "--apply"]) == 2
    assert "--acl-reviewed" in capsys.readouterr().err
