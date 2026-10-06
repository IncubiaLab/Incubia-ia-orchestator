from incubia_orchestrator.bootstrap.composition import _load_local_env


def test_local_env_loads_supported_keys_without_overriding_shell(monkeypatch, tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('OPENAI_API_KEY=file-key\nINCUBIA_MODEL=gpt-4o-mini\nIGNORED=secret\n')
    monkeypatch.setenv('INCUBIA_ENV_FILE', str(env_file))
    monkeypatch.setenv('OPENAI_API_KEY', 'shell-key')
    monkeypatch.delenv('INCUBIA_MODEL', raising=False)
    monkeypatch.delenv('IGNORED', raising=False)
    _load_local_env()
    import os
    assert os.environ['OPENAI_API_KEY'] == 'shell-key'
    assert os.environ['INCUBIA_MODEL'] == 'gpt-4o-mini'
    assert 'IGNORED' not in os.environ
