"""Project-local namespace used to isolate local knowledge-base metadata."""

from __future__ import annotations

import hashlib
import os

from app.utils.path_config import PROJECT_ROOT


def get_local_knowledge_scope() -> str:
    """Return a stable, deployment-overridable namespace for local indexes.

    Worktrees have distinct absolute project roots, so the derived value keeps
    their local metadata isolated even when they point at one PostgreSQL DB.
    Production can set ``KNOWLEDGE_BASE_LOCAL_SCOPE`` to a human-managed ID.
    """
    configured = os.getenv("KNOWLEDGE_BASE_LOCAL_SCOPE", "").strip()
    if configured:
        return configured[:128]
    digest = hashlib.sha256(str(PROJECT_ROOT).encode("utf-8")).hexdigest()[:16]
    return f"workspace-{digest}"
