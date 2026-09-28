from pathlib import Path

import pytest

from app.approval_cli import build_token
from app.approvals import ApprovalError, ApprovalVerifier, create_approval_token


def make_verifier(tmp_path: Path) -> ApprovalVerifier:
    return ApprovalVerifier("x" * 32, tmp_path / "approvals.sqlite3")


def test_approval_is_scoped_to_exact_action_and_target(tmp_path):
    verifier = make_verifier(tmp_path)
    token = create_approval_token("x" * 32, "workspace.delete", "old.txt", 60)
    with pytest.raises(ApprovalError, match="scope"):
        verifier.verify(token, "git.push", "old.txt")


def test_approval_is_single_use(tmp_path):
    verifier = make_verifier(tmp_path)
    token = create_approval_token("x" * 32, "workspace.delete", "old.txt", 60)
    verifier.verify(token, "workspace.delete", "old.txt")
    with pytest.raises(ApprovalError, match="already used"):
        verifier.verify(token, "workspace.delete", "old.txt")


def test_expired_approval_is_rejected(tmp_path):
    verifier = make_verifier(tmp_path)
    token = create_approval_token("x" * 32, "workspace.delete", "old.txt", -1)
    with pytest.raises(ApprovalError, match="expired"):
        verifier.verify(token, "workspace.delete", "old.txt")


def test_local_helper_builds_scoped_token_without_echoing_secret(tmp_path):
    secret = "s" * 32
    token = build_token(secret, "git.push", "feature/test", 60)

    claims = ApprovalVerifier(secret, tmp_path / "used.sqlite3").verify(
        token, "git.push", "feature/test"
    )

    assert claims.action == "git.push"
    assert secret not in token
