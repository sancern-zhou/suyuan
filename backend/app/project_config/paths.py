"""Resolve project-owned directories declared by the active manifest."""
from pathlib import Path

from app.utils.path_config import format_agent_path, is_path_within, resolve_agent_path

from .loader import ProjectConfigError
from .models import ProjectContext


def project_skills_dir(context: ProjectContext) -> Path:
    """Return the isolated skill directory for a project.

    Projects which do not opt in keep the legacy shared skills directory for
    backwards compatibility.  A configured directory must stay project-owned.
    """
    configured = context.manifest.backend.skills_dir
    if not configured:
        return resolve_agent_path("backend/docs/skills")

    project_root = resolve_agent_path(f"projects/{context.manifest.project}")
    skills_dir = resolve_agent_path(configured)
    if not is_path_within(skills_dir, [project_root]):
        raise ProjectConfigError(
            "skills_dir must be inside "
            f"projects/{context.manifest.project}: {format_agent_path(skills_dir)}"
        )
    if not skills_dir.is_dir():
        raise ProjectConfigError(f"skills_dir not found: {format_agent_path(skills_dir)}")
    return skills_dir
