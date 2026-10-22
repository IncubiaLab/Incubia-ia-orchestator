"""Behaviour contract for scripts/e3/neon_branch_guard.py.

This module guards every RAG-V1 / E3 Neon campaign runner against being
pointed at a shared/production branch. The user supplied the branch name
`production` for RAG-V1 work; that branch must be structurally impossible to
use, both as a target branch and as a whitelisted `expected` value.
"""
from __future__ import annotations

import pytest

from scripts.e3.neon_branch_guard import (
    BranchGuardError,
    PROHIBITED_BRANCHES,
    guard_campaign_environment,
    require_isolated_branch,
    sanitize_dsn_reference,
)


# --- require_isolated_branch: missing name ----------------------------------

def test_none_branch_is_rejected():
    with pytest.raises(BranchGuardError, match="must be named explicitly"):
        require_isolated_branch(None)


def test_empty_branch_is_rejected():
    with pytest.raises(BranchGuardError, match="must be named explicitly"):
        require_isolated_branch("")


def test_whitespace_only_branch_is_rejected():
    with pytest.raises(BranchGuardError, match="must be named explicitly"):
        require_isolated_branch("   ")


# --- require_isolated_branch: prohibited branches ---------------------------

def test_production_branch_is_rejected():
    with pytest.raises(BranchGuardError):
        require_isolated_branch("production")


@pytest.mark.parametrize("name", ["Production", " production ", "PRODUCTION"])
def test_production_variants_are_rejected_case_and_whitespace_insensitively(name):
    with pytest.raises(BranchGuardError):
        require_isolated_branch(name)


@pytest.mark.parametrize("name", sorted(PROHIBITED_BRANCHES))
def test_every_prohibited_branch_is_rejected(name):
    with pytest.raises(BranchGuardError):
        require_isolated_branch(name)


# --- require_isolated_branch: unsafe slug -----------------------------------

@pytest.mark.parametrize("name", ["ab", "feat_knowledge_base", "-feat-kb", "feat kb", "has/slash"])
def test_unsafe_branch_slug_is_rejected(name):
    with pytest.raises(BranchGuardError):
        require_isolated_branch(name)


# --- require_isolated_branch: expected mismatch -----------------------------

def test_expected_mismatch_is_rejected():
    with pytest.raises(BranchGuardError):
        require_isolated_branch("feat-knowledge-base", expected="e3-h1-synthetic")


def test_prohibited_name_cannot_be_whitelisted_via_expected():
    # Ruling B: a prohibited name must stay rejected even if it is also
    # passed (identically) as the `expected` value.
    with pytest.raises(BranchGuardError):
        require_isolated_branch("production", expected="production")


# --- require_isolated_branch: success ---------------------------------------

def test_dedicated_branch_is_accepted_and_normalised():
    assert require_isolated_branch(" Feat-Knowledge-Base ", expected="feat-knowledge-base") == "feat-knowledge-base"


def test_default_dedicated_branch_constant_is_accepted():
    assert require_isolated_branch("feat-knowledge-base") == "feat-knowledge-base"


# --- guard_campaign_environment ---------------------------------------------

def test_guard_campaign_environment_requires_authorization_flag():
    env = {"INCUBIA_E3_NEON_BRANCH": "e3-h1-synthetic"}
    with pytest.raises(BranchGuardError):
        guard_campaign_environment(env, expected_branch="e3-h1-synthetic")


def test_guard_campaign_environment_rejects_wrong_authorization_value():
    env = {"INCUBIA_E3_NEON_TESTS": "yes", "INCUBIA_E3_NEON_BRANCH": "e3-h1-synthetic"}
    with pytest.raises(BranchGuardError):
        guard_campaign_environment(env, expected_branch="e3-h1-synthetic")


def test_guard_campaign_environment_rejects_prohibited_branch_even_when_authorized():
    env = {"INCUBIA_E3_NEON_TESTS": "1", "INCUBIA_E3_NEON_BRANCH": "production"}
    with pytest.raises(BranchGuardError):
        guard_campaign_environment(env, expected_branch="production")


def test_guard_campaign_environment_returns_validated_branch():
    env = {"INCUBIA_E3_NEON_TESTS": "1", "INCUBIA_E3_NEON_BRANCH": "e3-h1-synthetic"}
    assert guard_campaign_environment(env, expected_branch="e3-h1-synthetic") == "e3-h1-synthetic"


def test_guard_campaign_environment_uses_custom_authorization_flag():
    env = {"RAG_V1_NEON_TESTS": "1", "INCUBIA_E3_NEON_BRANCH": "feat-knowledge-base"}
    assert guard_campaign_environment(
        env, expected_branch="feat-knowledge-base", authorization_flag="RAG_V1_NEON_TESTS"
    ) == "feat-knowledge-base"


# --- sanitize_dsn_reference ---------------------------------------------------

def test_sanitize_dsn_reference_strips_password_and_query_and_digests_host():
    dsn = (
        "postgres://dbuser@ep-still-cell-b5cvn1vh.us-east-2.aws.neon.tech/neondb"
        "?password=hunter2&sslmode=require&options=secret"
    )
    result = sanitize_dsn_reference(dsn)
    assert "hunter2" not in result
    assert "password=hunter2" not in result
    assert "sslmode=require" not in result
    assert "options=secret" not in result
    assert "ep-still-cell-b5cvn1vh" not in result
    assert result.startswith("postgres://dbuser@")
    assert result.endswith("/neondb")


def test_sanitize_dsn_reference_rejects_non_postgres_scheme():
    with pytest.raises(BranchGuardError):
        sanitize_dsn_reference("mysql://user@host.neon.tech/db")


def test_sanitize_dsn_reference_rejects_non_neon_host():
    with pytest.raises(BranchGuardError):
        sanitize_dsn_reference("postgres://user@example.com/db")


def test_sanitize_dsn_reference_rejects_password_smuggled_into_database_segment():
    with pytest.raises(BranchGuardError):
        sanitize_dsn_reference("postgres://user@host.neon.tech/db;password=hunter2")
