from incubia_orchestrator.interfaces.cli.bot import _load_bindings, _load_telegram_env


def test_telegram_env_loads_only_the_bot_token(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=test-token\nIGNORED=value\n")
    monkeypatch.setenv("INCUBIA_ENV_FILE", str(env_file))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("IGNORED", raising=False)
    _load_telegram_env()
    import os
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "test-token"
    assert "IGNORED" not in os.environ


def test_private_pilot_requires_exactly_two_distinct_tenants(tmp_path):
    path = tmp_path / "bindings.yaml"
    path.write_text("""contract_version: 1
bindings:
  - {channel: telegram, channel_account_ref: bot, external_chat_ref: c1, external_sender_ref: s1, deployment_id: d, tenant_id: t1, conversation_id: x1, actor_id: a1}
  - {channel: telegram, channel_account_ref: bot, external_chat_ref: c2, external_sender_ref: s2, deployment_id: d, tenant_id: t2, conversation_id: x2, actor_id: a2}
""")
    assert len(_load_bindings(path)) == 2
