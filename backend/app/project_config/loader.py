from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ModuleManifest, ProjectContext, ProjectManifest, validate_identifier

# libyaml-backed loader when available: pure-Python safe_load spends ~67 ms on the
# 36 KB Guangdong manifest, which agents pay on every planner iteration.
_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_CONTEXT_CACHE: dict[
    tuple[str, str], tuple[tuple[tuple[str, int, int], ...], ProjectContext]
] = {}


class ProjectConfigError(RuntimeError):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ProjectConfigError(f"manifest not found: {path}")
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_YAML_LOADER)
    except yaml.YAMLError as exc:
        raise ProjectConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectConfigError(f"manifest must be an object: {path}")
    return value


def _manifest_signature(
    root: Path, project_id: str, module_ids: tuple[str, ...] | list[str]
) -> tuple[tuple[str, int, int], ...]:
    """Cheap change detector: (path, mtime_ns, size) for every manifest read."""
    paths = [root / "projects" / project_id / "project.yaml"]
    paths.extend(root / "modules" / module_id / "module.yaml" for module_id in module_ids)
    signature: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            signature.append((str(path), -1, -1))
        else:
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def load_project_context(project_id: str, *, repo_root: Path | None = None) -> ProjectContext:
    try:
        validate_identifier(project_id)
    except ValueError as exc:
        raise ProjectConfigError(str(exc)) from exc

    root = (repo_root or repository_root()).resolve()
    cache_key = (str(root), project_id)
    cached = _CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        cached_signature, cached_context = cached
        current_signature = _manifest_signature(
            root, project_id, cached_context.manifest.modules
        )
        if current_signature == cached_signature:
            return cached_context

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

    context = ProjectContext(
        manifest=project,
        module_manifests=modules,
        enabled_modules=frozenset({"core", *selected}),
    )
    # Callers only read the context; the signature guards against manifest edits
    # so a cached instance never outlives the files it was built from.
    _CONTEXT_CACHE[cache_key] = (
        _manifest_signature(root, project_id, project.modules),
        context,
    )
    return context
