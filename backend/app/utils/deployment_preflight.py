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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    try:
        registry = configured_data_registry(args.env_file)
    except DeploymentConfigError as exc:
        parser.error(str(exc))
    print(f"[INFO] Data registry: {registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
