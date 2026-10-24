import pytest

from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import (
    ENV_VAR, KnowledgeDsnError, knowledge_runtime_resolver)

GOOD = ("postgresql://incubia_kb_runtime:s3cretpassword@ep-x-pooler.us-east-2.aws.neon.tech/"
        "incubialab_knowledge_dev?sslmode=require")


def test_resolves_only_the_trusted_deployment():
    resolve = knowledge_runtime_resolver({ENV_VAR: GOOD}, deployment_id="incubialab")
    assert resolve("incubialab") == GOOD
    assert resolve("other") == ""
    assert resolve("") == ""


@pytest.mark.parametrize("dsn", [
    "",
    GOOD.replace("incubia_kb_runtime", "incubia_kb_ingestor"),
    GOOD.replace("-pooler.", "."),
    GOOD.replace(".neon.tech", ".example.com"),
    GOOD.replace("sslmode=require", "sslmode=prefer"),
    GOOD.replace("postgresql://", "mysql://"),
    GOOD.replace("s3cretpassword", "REPLACE_ME"),
    GOOD.replace("/incubialab_knowledge_dev", "/"),
])
def test_rejects_unsafe_dsn_without_echoing_it(dsn):
    with pytest.raises(KnowledgeDsnError) as error:
        knowledge_runtime_resolver({ENV_VAR: dsn}, deployment_id="incubialab")
    assert "s3cretpassword" not in str(error.value)
    assert "neon.tech" not in str(error.value)


def test_requires_deployment_id():
    with pytest.raises(KnowledgeDsnError):
        knowledge_runtime_resolver({ENV_VAR: GOOD}, deployment_id="")


def test_ingest_resolver_requires_ingestor_role():
    from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import (
        INGEST_ENV_VAR, knowledge_ingest_resolver)
    ingest = GOOD.replace("incubia_kb_runtime", "incubia_kb_ingestor")
    resolve = knowledge_ingest_resolver({INGEST_ENV_VAR: ingest}, deployment_id="incubialab")
    assert resolve("incubialab") == ingest and resolve("other") == ""
    with pytest.raises(KnowledgeDsnError):
        knowledge_ingest_resolver({INGEST_ENV_VAR: GOOD}, deployment_id="incubialab")
