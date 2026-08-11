"""Load project-owned agent mode prompts declared by the active project."""

from app.project_config import ProjectConfigError, ProjectContext, load_project_context
from app.utils.path_config import format_agent_path, is_path_within, resolve_agent_path
from config.settings import settings


def load_project_mode_prompt(
    mode: str,
    context: ProjectContext | None = None,
) -> str | None:
    """Return the active project's prompt override for ``mode``, if configured."""
    project_context = context or load_project_context(settings.project_id)
    configured_path = project_context.manifest.backend.mode_prompt_files.get(mode)
    if not configured_path:
        return None

    project_root = resolve_agent_path(f"projects/{project_context.manifest.project}")
    prompt_path = resolve_agent_path(configured_path)
    if not is_path_within(prompt_path, [project_root]):
        raise ProjectConfigError(
            f"mode prompt must be inside projects/{project_context.manifest.project}: "
            f"{format_agent_path(prompt_path)}"
        )
    if not prompt_path.is_file():
        raise ProjectConfigError(f"mode prompt not found: {format_agent_path(prompt_path)}")

    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ProjectConfigError(f"mode prompt is empty: {format_agent_path(prompt_path)}")
    return prompt
