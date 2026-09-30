from pathlib import Path

import pytest

from app.utils.deployment_preflight import (
    DeploymentConfigError,
    configured_data_registry,
    configured_python_sandbox_cgroup,
)


def test_data_registry_must_be_explicit(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("PROJECT=default\n", encoding="utf-8")

    with pytest.raises(DeploymentConfigError, match="must be set explicitly"):
        configured_data_registry(env_file, environ={})


def test_data_registry_must_be_absolute(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DATA_REGISTRY_DIR=backend_data_registry\n", encoding="utf-8")

    with pytest.raises(DeploymentConfigError, match="must be an absolute path"):
        configured_data_registry(env_file, environ={})


def test_data_registry_accepts_absolute_env_file_value(tmp_path: Path):
    registry = tmp_path / "registry"
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATA_REGISTRY_DIR={registry}\n", encoding="utf-8")

    assert configured_data_registry(env_file, environ={}) == registry.resolve()


def test_process_environment_takes_precedence(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DATA_REGISTRY_DIR=relative-path\n", encoding="utf-8")
    registry = tmp_path / "registry"

    assert configured_data_registry(
        env_file, environ={"DATA_REGISTRY_DIR": str(registry)}
    ) == registry.resolve()


def test_python_sandbox_cgroup_is_optional(tmp_path: Path):
    assert configured_python_sandbox_cgroup(
        tmp_path / ".env", environ={}, cgroup_root=tmp_path / "cgroup"
    ) is None


def test_python_sandbox_cgroup_must_be_under_v2_root(tmp_path: Path):
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text("memory pids", encoding="ascii")
    with pytest.raises(DeploymentConfigError, match="inside the cgroup v2 root"):
        configured_python_sandbox_cgroup(
            environ={"PYTHON_SANDBOX_CGROUP_PARENT": str(tmp_path / "outside")},
            cgroup_root=root,
        )


def test_python_sandbox_cgroup_accepts_delegated_parent(tmp_path: Path):
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text("memory pids", encoding="ascii")
    parent = root / "suyuan-execute-python"
    assert configured_python_sandbox_cgroup(
        environ={"PYTHON_SANDBOX_CGROUP_PARENT": str(parent)},
        cgroup_root=root,
    ) == parent.resolve()
