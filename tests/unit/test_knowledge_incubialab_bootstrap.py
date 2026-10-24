import pytest

from incubia_orchestrator.bootstrap.knowledge_incubialab import (
    DEPLOYMENT_ENV_VAR, compose_incubialab_retrieval)
from incubia_orchestrator.modules.knowledge.adapters.embedding import HashEmbedding
from incubia_orchestrator.modules.knowledge.adapters.postgres import PostgresKnowledge
from incubia_orchestrator.modules.knowledge.adapters.runtime_dsn import ENV_VAR, KnowledgeDsnError

GOOD = ("postgresql://incubia_kb_runtime:s3cretpassword@ep-x-pooler.us-east-2.aws.neon.tech/"
        "incubialab_knowledge_dev?sslmode=require")


def test_composes_postgres_retrieval_without_connecting():
    knowledge = compose_incubialab_retrieval({DEPLOYMENT_ENV_VAR: "incubialab", ENV_VAR: GOOD},
                                             HashEmbedding())
    assert isinstance(knowledge, PostgresKnowledge)


@pytest.mark.parametrize("env", [{ENV_VAR: GOOD}, {DEPLOYMENT_ENV_VAR: "incubialab"},
                                 {DEPLOYMENT_ENV_VAR: "incubialab", ENV_VAR: GOOD.replace("-pooler.", ".")}])
def test_fails_closed_without_deployment_or_valid_dsn(env):
    with pytest.raises(KnowledgeDsnError):
        compose_incubialab_retrieval(env, HashEmbedding())
