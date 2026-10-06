"""Validate deployment settings that must not depend on the checkout location."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


class DeploymentConfigError(ValueError):
    """Raised when a deployment setting could make persisted paths unstable."""


def configured_data_registry(
    env_file: str | Path = ".env",
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the explicitly configured, absolute data registry directory."""
    environment = os.environ if environ is None else environ
    configured = environment.get("DATA_REGISTRY_DIR")
    if not configured:
        configured = dotenv_values(Path(env_file)).get("DATA_REGISTRY_DIR")
    raw_path = str(configured or "").strip()
    if not raw_path:
        raise DeploymentConfigError(
            "DATA_REGISTRY_DIR must be set explicitly in the deployment env file"
        )

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        raise DeploymentConfigError(
            "DATA_REGISTRY_DIR must be an absolute path so it does not change "
            "when the service starts from another Git worktree"
        )
    return candidate.resolve()


def configured_python_sandbox_cgroup(
    env_file: str | Path = ".env",
    *,
    environ: Mapping[str, str] | None = None,
    cgroup_root: str | Path = "/sys/fs/cgroup",
) -> Path | None:
    """Validate an optional delegated cgroup v2 parent for execute_python."""
    environment = os.environ if environ is None else environ
    configured = environment.get("PYTHON_SANDBOX_CGROUP_PARENT")
    if configured is None:
        configured = dotenv_values(Path(env_file)).get("PYTHON_SANDBOX_CGROUP_PARENT")
    raw_path = str(configured or "").strip()
    if not raw_path:
        return None

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        raise DeploymentConfigError("PYTHON_SANDBOX_CGROUP_PARENT must be an absolute path")
    root = Path(cgroup_root).resolve()
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise DeploymentConfigError(
            f"PYTHON_SANDBOX_CGROUP_PARENT must be inside the cgroup v2 root: {root}"
        )
    if not (root / "cgroup.controllers").is_file():
        raise DeploymentConfigError(f"cgroup v2 is not available at {root}")

    writable_ancestor = resolved
    while not writable_ancestor.exists() and writable_ancestor != root:
        writable_ancestor = writable_ancestor.parent
    if not writable_ancestor.exists() or not os.access(writable_ancestor, os.W_OK):
        raise DeploymentConfigError(
            f"PYTHON_SANDBOX_CGROUP_PARENT is not delegated/writable: {resolved}"
        )
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    try:
        registry = configured_data_registry(args.env_file)
        cgroup_parent = configured_python_sandbox_cgroup(args.env_file)
    except DeploymentConfigError as exc:
        parser.error(str(exc))
    print(f"[INFO] Data registry: {registry}")
    if cgroup_parent is not None:
        print(f"[INFO] Python sandbox cgroup: {cgroup_parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
