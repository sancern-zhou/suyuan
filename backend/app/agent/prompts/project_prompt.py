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


def load_project_audience_contract(
    context: ProjectContext | None = None,
) -> str | None:
    """Return the active project's audience contract text, if configured.

    平台提示词的"用户面向与表达约定"段落按项目提供；项目未声明时返回
    None，由调用方使用共享中性默认。共享默认不得写死任何项目地名
    （曾因共享常量写死"许昌市"，广东部署的子 Agent 把广东数据在交付
    摘要里标成"许昌市气象实况"）。
    """
    project_context = context or load_project_context(settings.project_id)
    configured_path = project_context.manifest.backend.audience_contract_file
    if not configured_path:
        return None

    project_root = resolve_agent_path(f"projects/{project_context.manifest.project}")
    contract_path = resolve_agent_path(configured_path)
    if not is_path_within(contract_path, [project_root]):
        raise ProjectConfigError(
            f"audience contract must be inside projects/{project_context.manifest.project}: "
            f"{format_agent_path(contract_path)}"
        )
    if not contract_path.is_file():
        raise ProjectConfigError(f"audience contract not found: {format_agent_path(contract_path)}")

    contract = contract_path.read_text(encoding="utf-8").strip()
    if not contract:
        raise ProjectConfigError(f"audience contract is empty: {format_agent_path(contract_path)}")
    return contract


def load_project_prompt_fragment(
    segment_id: str,
    context: ProjectContext | None = None,
) -> str | None:
    """Return the active project's prompt fragment for ``segment_id``, if configured.

    共享 prompt builder 在固定锚点追加"项目补充口径"段落：项目专属的路由规则、
    中台视图与地名口径只允许写在 projects/<id>/ 的片段文件里（backend.
    prompt_fragment_files 声明），共享 builder 不写死任何项目内容。项目未声明
    该锚点时返回 None，builder 保持共享中性默认。
    """
    project_context = context or load_project_context(settings.project_id)
    configured_path = project_context.manifest.backend.prompt_fragment_files.get(segment_id)
    if not configured_path:
        return None

    project_root = resolve_agent_path(f"projects/{project_context.manifest.project}")
    fragment_path = resolve_agent_path(configured_path)
    if not is_path_within(fragment_path, [project_root]):
        raise ProjectConfigError(
            f"prompt fragment must be inside projects/{project_context.manifest.project}: "
            f"{format_agent_path(fragment_path)}"
        )
    if not fragment_path.is_file():
        raise ProjectConfigError(f"prompt fragment not found: {format_agent_path(fragment_path)}")

    fragment = fragment_path.read_text(encoding="utf-8").strip()
    if not fragment:
        raise ProjectConfigError(f"prompt fragment is empty: {format_agent_path(fragment_path)}")
    return fragment
