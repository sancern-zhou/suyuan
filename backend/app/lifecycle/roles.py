"""Application role helpers for multi-process deployments."""

from __future__ import annotations

VALID_APP_ROLES = {"web", "worker", "all"}


def normalize_app_role(raw_role: str | None) -> str:
    """Return a supported application role.

    web:
        HTTP/API process. Safe to run with multiple uvicorn workers.
    worker:
        Single background process for schedulers, fetchers, social bridge, and
        knowledge-base queues.
    all:
        Legacy single-process mode that runs HTTP and background services
        together. Do not use with multiple uvicorn workers.
    """
    role = (raw_role or "web").strip().lower()
    if role not in VALID_APP_ROLES:
        raise ValueError(f"Unsupported APP_ROLE '{raw_role}'. Expected one of: web, worker, all")
    return role


def starts_background_services(role: str) -> bool:
    return normalize_app_role(role) in {"worker", "all"}
