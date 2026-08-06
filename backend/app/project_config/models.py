import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"invalid project identifier: {value!r}")
    return value


def unique(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("duplicate entries are not allowed")
    return values


def valid_identifier_map(value: dict[str, Any]) -> dict[str, Any]:
    for key in value:
        validate_identifier(key)
    return value


def unique_string_lists(value: dict[str, list[str]]) -> dict[str, list[str]]:
    for key, values in value.items():
        validate_identifier(key)
        unique(values)
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrontendManifest(StrictModel):
    theme: str = "default"
    brand_name: str = "风清气智"
    features: dict[str, bool] = Field(default_factory=dict)
    agent_modes: list[str] = Field(default_factory=list)
    default_agent_mode: str | None = None
    agent_mode_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    agent_platform_layout: Literal["scenes", "environment-grid"] = "scenes"

    _unique_agent_modes = field_validator("agent_modes")(unique)
    _valid_agent_mode_overrides = field_validator("agent_mode_overrides")(valid_identifier_map)

    @model_validator(mode="after")
    def validate_default_agent_mode(self):
        if self.default_agent_mode is None:
            return self
        validate_identifier(self.default_agent_mode)
        if self.agent_modes and self.default_agent_mode not in self.agent_modes:
            raise ValueError("default_agent_mode must be declared in agent_modes")
        return self


class BackendManifest(StrictModel):
    tools: list[str] = Field(default_factory=list)
    fetchers_enabled: bool = True
    gis_tools_enabled: bool = True
    mode_prompt_files: dict[str, str] = Field(default_factory=dict)
    agent_mode_tools: dict[str, list[str]] = Field(default_factory=dict)

    _unique_tools = field_validator("tools")(unique)
    _valid_mode_prompt_files = field_validator("mode_prompt_files")(valid_identifier_map)
    _unique_agent_mode_tools = field_validator("agent_mode_tools")(unique_string_lists)


class KnowledgeManifest(StrictModel):
    collections: list[str] = Field(default_factory=list)

    _unique_collections = field_validator("collections")(unique)


class ProjectManifest(StrictModel):
    schema_version: Literal[1]
    project: str
    modules: list[str] = Field(default_factory=list)
    frontend: FrontendManifest = Field(default_factory=FrontendManifest)
    backend: BackendManifest = Field(default_factory=BackendManifest)
    knowledge: KnowledgeManifest = Field(default_factory=KnowledgeManifest)
    scheduled_tasks: list[str] = Field(default_factory=list)

    _valid_project = field_validator("project")(validate_identifier)
    _unique_modules = field_validator("modules")(unique)
    _unique_tasks = field_validator("scheduled_tasks")(unique)


class ModuleManifest(StrictModel):
    schema_version: Literal[1]
    module: str
    dependencies: list[str] = Field(default_factory=list)

    _valid_module = field_validator("module")(validate_identifier)
    _unique_dependencies = field_validator("dependencies")(unique)


class ProjectContext(StrictModel):
    manifest: ProjectManifest
    module_manifests: dict[str, ModuleManifest]
    enabled_modules: frozenset[str]
