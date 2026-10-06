"""Shared agent file-read policy (path_config) contract tests."""
import pytest

from app.utils.path_config import (
    agent_content_read_roots,
    agent_declared_input_roots,
    describe_agent_read_policy,
    get_data_registry,
    is_agent_readable_path,
)


def test_content_read_roots_cover_project_temp_and_registry():
    roots = agent_content_read_roots()
    assert any(root == get_data_registry() for root in roots)


def test_declared_input_roots_exclude_temp(tmp_path):
    # /tmp staging files must never be declarable sandbox inputs.
    roots = agent_declared_input_roots()
    assert not any(
        tmp_path.resolve().is_relative_to(root.resolve()) for root in roots
    )


def test_sensitive_paths_are_never_readable(tmp_path):
    secret = tmp_path / ".env"
    secret.write_text("SECRET=1")
    key = tmp_path / "id_rsa"
    key.write_text("key")
    for path in (secret, key):
        assert is_agent_readable_path(path) is False
        assert is_agent_readable_path(path, extra_allowed=[tmp_path]) is False


def test_extra_allowed_extends_content_roots():
    # Synthetic location outside every content root (not /tmp, not the repo).
    outside = "/var/vault_demo/upload.json"
    assert is_agent_readable_path(outside) is False
    assert is_agent_readable_path(outside, extra_allowed=[outside]) is True


def test_policy_text_mentions_registry_and_session():
    text = describe_agent_read_policy()
    assert "会话" in text
    assert "数据注册表" in text
