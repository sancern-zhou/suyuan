"""Provider registry and project-based provider selection.

Project branches register their provider here (usually at tool registration
time).  Tools then ask for "the provider for the current project" instead of
hard-coding a region, which is what made the old tools non-portable.
"""

from __future__ import annotations

from collections.abc import Iterable

from .errors import StationDirectoryNotFound
from .provider import StationDirectoryProvider


class StationDirectoryRegistry:
    """Keeps providers and maps projects to a provider name."""

    def __init__(self) -> None:
        self._providers: dict[str, StationDirectoryProvider] = {}
        self._project_bindings: dict[str, str] = {}
        self._default_provider: str | None = None

    def register(
        self,
        provider: StationDirectoryProvider,
        *,
        projects: Iterable[str] | None = None,
        default: bool = False,
    ) -> StationDirectoryProvider:
        name = str(provider.name or "").strip()
        if not name:
            raise StationDirectoryNotFound("provider name is required")
        self._providers[name] = provider
        for project in projects or ():
            key = str(project or "").strip()
            if key:
                self._project_bindings[key] = name
        if default or self._default_provider is None:
            self._default_provider = name
        return provider

    def get(self, name: str) -> StationDirectoryProvider:
        provider = self._providers.get(str(name or "").strip())
        if provider is None:
            raise StationDirectoryNotFound(f"未注册的站点目录 provider: {name}")
        return provider

    def for_project(self, project_id: str | None = None) -> StationDirectoryProvider | None:
        key = str(project_id or "").strip()
        if key and key in self._project_bindings:
            return self._providers.get(self._project_bindings[key])
        if self._default_provider is not None:
            return self._providers.get(self._default_provider)
        return None

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def clear(self) -> None:
        self._providers.clear()
        self._project_bindings.clear()
        self._default_provider = None


_registry = StationDirectoryRegistry()


def get_station_directory_registry() -> StationDirectoryRegistry:
    return _registry


def get_station_directory_provider(
    project_id: str | None = None,
) -> StationDirectoryProvider | None:
    """Return the provider bound to ``project_id`` (or the default)."""

    if project_id is None:
        try:
            from config.settings import settings

            project_id = settings.project_id
        except Exception:  # pragma: no cover - settings always importable in app
            project_id = None
    return _registry.for_project(project_id)
