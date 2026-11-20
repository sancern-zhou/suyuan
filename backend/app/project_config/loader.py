from copy import deepcopy
from pathlib import Path
from threading import Lock

import yaml
from pydantic import ValidationError

from .models import ModuleManifest, ProjectContext, ProjectManifest, validate_identifier


class ProjectConfigError(RuntimeError):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


# 提示词/工具构建会多次解析同一清单（一次 build 约 9 次），每次 YAML 解析
# 约 14ms，是热路径主要开销。这里按（路径, mtime, size）缓存原始解析结果，
# 每次仍重新校验成新模型，避免调用方原地修改污染后续调用。
_YAML_CACHE: dict[Path, tuple[tuple[int, int], dict]] = {}
_YAML_CACHE_LOCK = Lock()


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ProjectConfigError(f"manifest not found: {path}")
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    with _YAML_CACHE_LOCK:
        cached = _YAML_CACHE.get(path)
    if cached is not None and cached[0] == signature:
        return deepcopy(cached[1])
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectConfigError(f"manifest must be an object: {path}")
    with _YAML_CACHE_LOCK:
        _YAML_CACHE[path] = (signature, value)
    return deepcopy(value)


def load_project_context(project_id: str, *, repo_root: Path | None = None) -> ProjectContext:
    try:
        validate_identifier(project_id)
    except ValueError as exc:
        raise ProjectConfigError(str(exc)) from exc

    root = (repo_root or repository_root()).resolve()
    project_path = root / "projects" / project_id / "project.yaml"
    try:
        project = ProjectManifest.model_validate(_read_yaml(project_path))
    except ValidationError as exc:
        raise ProjectConfigError(f"invalid project manifest {project_path}: {exc}") from exc
    if project.project != project_id:
        raise ProjectConfigError(
            f"project manifest id {project.project!r} does not match directory {project_id!r}"
        )

    modules: dict[str, ModuleManifest] = {}
    for module_id in project.modules:
        module_path = root / "modules" / module_id / "module.yaml"
        if not module_path.is_file():
            raise ProjectConfigError(f"unknown module: {module_id}")
        try:
            module = ModuleManifest.model_validate(_read_yaml(module_path))
        except ValidationError as exc:
            raise ProjectConfigError(f"invalid module manifest {module_path}: {exc}") from exc
        if module.module != module_id:
            raise ProjectConfigError(
                f"module manifest id {module.module!r} does not match directory {module_id!r}"
            )
        modules[module_id] = module

    selected = set(project.modules)
    for module_id, module in modules.items():
        for dependency in module.dependencies:
            if dependency not in selected:
                raise ProjectConfigError(f"{module_id} requires {dependency}")

    return ProjectContext(
        manifest=project,
        module_manifests=modules,
        enabled_modules=frozenset({"core", *selected}),
    )
