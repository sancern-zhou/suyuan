"""Bounded discovery of resource references crossing a tool boundary."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Iterable

from .contracts import ResourceDeclaration, ResourceLocator
from .models import ResourceKind, ResourceRole


_PATH_KEYS = {
    "path", "file", "file_path", "filepath", "output_file", "output_path",
    "preview_path", "pdf_path", "image_path", "montage_path", "directory",
    "output_dir", "preview_dir", "artifact_path", "download_path",
}
_URL_KEYS = {"url", "file_url", "preview_url", "download_url", "html_url", "pdf_url"}
_ID_KINDS = {
    "data_id": ResourceKind.DATA,
    "artifact_id": ResourceKind.ARTIFACT,
    "visual_id": ResourceKind.VISUAL,
}
_NON_CATALOG_INPUT_TOOLS = {
    # Catalog/resource management is metadata-only.
    "list_session_resources",
    "read_session_resource",
    # Discovery tools can mention hundreds of paths/URLs. Their results remain
    # in the tool turn but must not become durable session resources.
    "list_directory",
    "search_files",
    "grep",
    "web_search",
    "web_fetch",
}


def _walk(value: Any, *, prefix: str = "", budget: list[int] | None = None):
    remaining = budget or [1000]
    if remaining[0] <= 0:
        return
    remaining[0] -= 1
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key)
            field = f"{prefix}.{name}" if prefix else name
            yield field, name.casefold(), child
            yield from _walk(child, prefix=field, budget=remaining)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value[:200]):
            yield from _walk(child, prefix=f"{prefix}[{index}]", budget=remaining)


def _iter_files(path: Path, *, expand_directories: bool, max_files: int) -> Iterable[Path]:
    if path.is_file() or not expand_directories:
        yield path
        return
    if not path.is_dir():
        return
    count = 0
    for child in sorted(path.rglob("*")):
        if count >= max_files:
            break
        if child.is_file() and not any(part.startswith(".") for part in child.parts):
            yield child
            count += 1


def _file_metadata(path: Path, source_field: str, *, directory_root: Path | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "auto_discovered": True,
        "source_field": source_field,
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }
    try:
        metadata["size"] = path.stat().st_size
    except OSError:
        pass
    if directory_root is not None:
        try:
            metadata["relative_path"] = str(path.relative_to(directory_root))
        except ValueError:
            pass
    return metadata


def discover_resource_declarations(
    value: Any,
    *,
    role: ResourceRole,
    tool_name: str,
    expand_directories: bool = False,
    max_files: int = 100,
) -> list[ResourceDeclaration]:
    """Discover only strongly-keyed, bounded resource references.

    Existing files are required for path references. Output directories are
    expanded so generated previews cannot disappear behind a directory-only
    tool result. Explicit ``resources`` declarations are handled separately.
    """
    if role != ResourceRole.OUTPUT and tool_name in _NON_CATALOG_INPUT_TOOLS:
        return []

    declarations: list[ResourceDeclaration] = []
    seen: set[tuple[str, str]] = set()
    for field, key, child in _walk(value):
        if key == "resources":
            continue
        values = child if isinstance(child, (list, tuple)) else [child]
        singular_key = key[:-1] if key.endswith("s") else key
        if singular_key in _ID_KINDS:
            for scalar in values[:200]:
                if not isinstance(scalar, str) or not scalar.strip():
                    continue
                kind = _ID_KINDS[singular_key]
                locator = ResourceLocator(**{singular_key: scalar.strip()})
                declaration = ResourceDeclaration(
                    kind=kind,
                    role=role,
                    label=scalar.strip(),
                    locator=locator,
                    metadata={"auto_discovered": True, "source_field": field},
                    tool_name=tool_name,
                )
                identity = declaration.catalog_key()
                if identity not in seen:
                    declarations.append(declaration)
                    seen.add(identity)
            continue
        if key in _URL_KEYS or key.endswith("_url") or key.endswith("_urls"):
            for scalar in values[:200]:
                if not isinstance(scalar, str) or not scalar.startswith(("http://", "https://")):
                    continue
                declaration = ResourceDeclaration(
                    kind=ResourceKind.URL,
                    role=role,
                    label=scalar.rsplit("/", 1)[-1] or scalar,
                    locator=ResourceLocator(url=scalar),
                    metadata={"auto_discovered": True, "source_field": field},
                    tool_name=tool_name,
                )
                identity = declaration.catalog_key()
                if identity not in seen:
                    declarations.append(declaration)
                    seen.add(identity)
            continue
        is_path_key = key in _PATH_KEYS or key.endswith(("_path", "_paths", "_dir", "_dirs"))
        if not is_path_key:
            continue
        for scalar in values[:200]:
            if not isinstance(scalar, str) or not scalar.strip():
                continue
            candidate = Path(scalar).expanduser()
            try:
                candidate = candidate.resolve()
            except OSError:
                continue
            if not candidate.exists():
                continue
            directory_root = candidate if candidate.is_dir() else None
            for path in _iter_files(candidate, expand_directories=expand_directories, max_files=max_files):
                declaration = ResourceDeclaration(
                    kind=ResourceKind.FILE,
                    role=role,
                    label=path.name or str(path),
                    locator=ResourceLocator(path=str(path)),
                    metadata=_file_metadata(path, field, directory_root=directory_root),
                    tool_name=tool_name,
                )
                identity = declaration.catalog_key()
                if identity not in seen:
                    declarations.append(declaration)
                    seen.add(identity)
    return declarations


def merge_declarations(*groups: Iterable[ResourceDeclaration]) -> list[ResourceDeclaration]:
    by_key: dict[tuple[str, str], ResourceDeclaration] = {}
    for group in groups:
        for declaration in group:
            by_key[declaration.catalog_key()] = declaration
    return list(by_key.values())
